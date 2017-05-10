'''
Class to cliamte data on the national (& sub national) scale
Peter Pfleiderer
peter.pfleiderer@climateanalytics.org
'''

import sys,glob,os,itertools,datetime,pickle
import numpy as np
from netCDF4 import Dataset,netcdftime,num2date
import pandas as pd
import random as random
from mpl_toolkits.basemap import Basemap
from shapely.geometry import Polygon, MultiPolygon
import matplotlib.pylab as plt 
import matplotlib as mpl
from matplotlib import ticker
from matplotlib.ticker import MaxNLocator
import seaborn as sns
from matplotlib.colors import ListedColormap

from matplotlib import rc
rc('text', usetex=True)

try:
	from unidecode import unidecode
except:
	pass

def depth(d, level=1):
    if not isinstance(d, dict) or not d:
        return level
    return max(depth(d[k], level + 1) for k in d)


class country_analysis(object):

	def __init__(self,iso,working_directory,seasons={'year':range(1,13)}):
		self._iso=iso
		self._working_directory=working_directory

		self._seasons=seasons

		self._masks={}
		self._DATA=[]
		self._regions={}

		if os.path.isdir(self._working_directory)==False:os.system('mkdir '+self._working_directory)
		if os.path.isdir(self._working_directory+'/masks')==False:os.system('mkdir '+self._working_directory+'/masks')
		if os.path.isdir(self._working_directory+'/plots')==False:os.system('mkdir '+self._working_directory+'/plots')
		if os.path.isdir(self._working_directory+'/raw')==False:os.system('mkdir '+self._working_directory+'/raw')
		if os.path.isdir(self._working_directory+'/area_average')==False:os.system('mkdir '+self._working_directory+'/area_average')


	def zip_it(self):
		os.chdir(self._working_directory)
		os.chdir('../')
		os.system('tar -zcf '+self._working_directory[0:-1]+'.tar.gz '+self._working_directory.split('/')[-2])

	def load_data(self,quiet=True):
		for file in glob.glob(self._working_directory+'/masks/'+self._iso+'*.nc*'):
			file_new=self._working_directory+'/masks'+file.split('masks')[-1]
			if quiet==False:print file_new
			self.load_masks(file_new)

		for file in glob.glob(self._working_directory+'/raw/*'):
			file_new=self._working_directory+'/raw'+file.split('raw')[-1]
			if quiet==False:print file_new
			nc_out=Dataset(file_new,"r")
			tags={}
			for key,val in zip(nc_out.getncattr('tags_keys').split('**'),nc_out.getncattr('tags_values').split('**')):
				tags[key]=val
			try:
				var_name=tags['original_var_name']
			except:
				var_name=tags['var_name']


			print file_new
			new_data=new_data_object(outer_self=self,**tags)
			new_data.add_data(raw=nc_out.variables[var_name][:,:,:],lat=nc_out.variables['lat'][:],lon=nc_out.variables['lon'][:],time=nc_out.variables['time'][:],year=nc_out.variables['year'][:],month=nc_out.variables['month'][:])
			try:
				new_data.add_data(day=nc_out.variables['day'][:])
			except:
				print 'no days'
			new_data.create_time_stamp()
				

		for file in glob.glob(self._working_directory+'/area_average/*'):
			mask_style=file.split('-')[-1].split('.')[0]
			name=file.split('-')[-2]

			file_new=self._working_directory+'/area_average'+file.split('area_average')[-1]
			if quiet==False:print file_new
			for data in self._DATA:
				if sorted(data.name.split('_'))==sorted(name.split('_')):
					table=pd.read_csv(file_new,sep=';')
					for key in table.keys():
						if key not in ['time','year','month','index']:
							if mask_style not in data.area_average.keys():	data.area_average[mask_style]={}
							if 'unidecode' in sys.modules:
								data.area_average[mask_style][unidecode(key)]=np.array(table[key])
							if 'unidecode' not in sys.modules:
								data.area_average[mask_style][key]=np.array(table[key])

		try:
			self.get_adm_polygons()
		except:
			pass

	def get_historical_extreme_events(self,path):
		table=pd.read_csv(path,sep=';').to_dict()
		event_groups={'flood':['flash floods','floods'],'drought':['drought']}
		extreme_events={}
		for event in ['flood','drought']:
			extreme_events[event]=[]
			for i in table['ID']:
				if table['country'][i]=='SEN':
					if len(set(table['type'][i].replace(' ','').split(',')).intersection(event_groups[event]))>=1:
						extreme_events[event].append({
							'start':table['start'][i],
							'end':table['end'][i],
							'region':table['region'][i],
							'description':table['type'][i],
							})

		self._extreme_events=extreme_events

	def data_summary(self):
		types=set([dd.data_type for dd in self._DATA])
		var_names=set([dd.var_name for dd in self._DATA])

		for data_type in types:
			print '\n***********',data_type,'***********'
			for var_name in var_names:
				if len(self.selection([data_type,var_name],show_selection=False))>0:
					print '_',var_name
					self.selection([data_type,var_name])

	def selection(self,filters,show_selection=True):
		selection=[]
		count=0
		for data in self._DATA:
			selected=True
			for key in filters:
				if key not in data.all_tags:
					selected=False
			if selected:
				selection.append(data)
				if show_selection==True:
					print count, data.name,min(data.year),max(data.year), data.index
				count+=1
		return selection

	def find_ensemble(self,filters,quiet=True):
		ensemble={}
		ensemble_mean=None
		for data in self._DATA:
			selected=True
			for key in filters:
				if key not in data.all_tags:
					selected=False
			if selected and data.model!='ensemble_mean':
				ensemble[data.model]=data
				if quiet==False:
					print data.model+': '+data.name+' '+str(min(data.year))+'-'+str(max(data.year))
			if selected and data.model=='ensemble_mean':
				ensemble_mean=data

		return ensemble,ensemble_mean

	def unit_conversions(self):
		for data in self._DATA:
			if data.var_name in ['tas','TXx']:
				if np.nanmean(data.raw)>100:
					data.raw-=273.15
					for mask_style in data.area_average.keys():
						for region in data.area_average[mask_style].keys():
							data.area_average[mask_style][region]-=273.15

	def get_warming_slices(self,GMT_path,warming_lvls=[1.5,2,2.5,3],ref_period=[1986,2006],model_real_name=None):
		self._warming_slices={}
		for data in self._DATA:
			if hasattr(data,'model'):
				if data.model not in self._warming_slices.keys() and data.model!='ensemble_mean':
					self._warming_slices[data.model]={}
					if data.scenario not in self._warming_slices[data.model].keys():
						self._warming_slices[data.model][data.scenario]={}

						# model names from cordex are not explicit!
						if model_real_name!=None:		model_name=model_real_name[data.model]
						if model_real_name==None:		model_name=data.model.lower()
						GMT=glob.glob(GMT_path+model_name+'.'+data.scenario+'.r1i*')
						if len(GMT)>0:
							nc_in=Dataset(GMT[0],"r")
							# handle time information
							time=nc_in.variables['time'][:]
							year=time/12
							# GMT
							GMT = nc_in.variables['tas_global'][:]	
							ave_window=20
							rmean=GMT.copy()*np.nan
							for i in range(19,len(rmean)):
								#print i-ave_window+1,i
								rmean[i]=GMT[i-ave_window:i].mean()
							try:
								ref_warming=rmean[np.where(year==ref_period[1])[0]][0]
							except:
								ref_warming=rmean[np.where(year==ref_period[1])[0]]
							rmean=rmean-ref_warming

							self._warming_slices[data.model][data.scenario]['ref']=ref_period
							for change in warming_lvls:
								# is this the warming level of the referene period?
								change_to_ref=change-0.61 
								closest=np.nanargmin(abs(rmean-change_to_ref))
								print data.model,change_to_ref,np.nanmin(abs(rmean-change_to_ref)),year[closest],rmean[closest]
								if np.nanmin(abs(rmean-change_to_ref))<0.1:
									print 'selected'
									self._warming_slices[data.model][data.scenario][str(change)]=[year[closest]-20,year[closest]]


	###########
	# masks
	###########

	def identify_grid(self,input_file,lat_name,lon_name):
		# get information about grid of input data
		nc_in=Dataset(input_file,'r')
		lat = nc_in.variables[lat_name][:]								
		lon = nc_in.variables[lon_name][:].squeeze()

		if len(lat.shape)==2:
			lat=lat[:,0]
			lon=lon[0,:]

		# formerly shift_lon
		if max(lon)>200:	lon_shift=-180.0
		else:				lon_shift=0.0	
		lon+=lon_shift

		nx = len(lon)	;	ny = len(lat)
		grid=str(ny)+'x'+str(nx)+'_lat_'+str(lat[0])+'_'+str(lat[-1])+'_lon_'+str(lon[0])+'_'+str(lon[-1])
		nc_in.close()

		return lon,lat,grid,lon_shift	

	def load_masks(self,mask_file):
		# load existing mask
		nc_mask=Dataset(mask_file,'r')

		grid=nc_mask.getncattr('original_grid')
		mask_style=nc_mask.getncattr('mask_style')

		if grid not in self._masks.keys():
			self._masks[grid]={}
		if mask_style not in self._masks[grid].keys():
			self._masks[grid][mask_style]={}

		self._masks[grid]['lat_mask'] = nc_mask.variables['lat'][:]  
		self._masks[grid]['lon_mask'] = nc_mask.variables['lon'][:] 

		# get all variables (regions)
		for name in nc_mask.variables.keys():
			if name not in ['lat','lon']:
				if 'unidecode' in sys.modules:
					self._masks[grid][mask_style][unidecode(name)] = nc_mask.variables[name][:,:]
					if unidecode(name) not in self._regions.keys(): self._regions[unidecode(name)]=name
				if 'unidecode' not in sys.modules:
					self._masks[grid][mask_style][name] = nc_mask.variables[name][:,:]

	def get_grid_polygons(self,grid,lon,lat,lon_shift):
		# loop over the grid to get grid polygons
		nx = len(lon)	;	ny = len(lat)

		grid_polygons = np.empty((nx,ny),dtype=Polygon)
		dx = np.zeros((nx))
		dy = np.zeros((ny))
		dx[1:] = np.abs(np.diff(lon,1))
		dx[0] = dx[1]
		dy[1:] = np.abs(np.diff(lat,1))
		dy[0] = dy[1]
		for i in range(nx):
			x1 = lon[i]-dx[i]/2.
			x2 = lon[i]+dx[i]/2.
			for j in range(ny):
				y1 = lat[j]-dy[j]/2.
				y2 = lat[j]+dy[j]/2.
				grid_polygons[i,j] = Polygon([(x1,y1),(x1,y2),(x2,y2),(x2,y1)])
				#grid_polygons[i,j] = Polygon([(y1,x1),(y1,x2),(y2,x2),(y2,x1)])

		# since the lon axis has been shifted, masks and outputs will have to be shifted as well. This shift is computed here
		lon-=lon_shift
		shift = len(lon)-np.where(lon==lon[0]-lon_shift)[0][0]

		self._masks[grid]['lat_mask']=lat
		self._masks[grid]['lon_mask']=lon

		return grid_polygons,shift

	def regrid_pop_mask(self,grid,lon,lat,shift,pop_mask_file,mask_style):
		# regrid population mask 
		mygrid=open(self._working_directory+'/masks/'+grid+'.txt','w')
		mygrid.write('gridtype=lonlat\nxsize='+str(len(lon))+'\nysize='+str(len(lat))+'\nxfirst='+str(lon[0])+'\nxinc='+str(np.mean(np.diff(lon,1)))+'\nyfirst='+str(lat[0])+'\nyinc='+str(np.mean(np.diff(lat,1))))
		mygrid.close()
		os.system('cdo remapbil,'+self._working_directory+'/masks/'+grid+'.txt '+pop_mask_file+' '+self._working_directory+'/masks/'+mask_style+'_'+grid+'.nc')	
		nc_pop_mask = Dataset(self._working_directory+'/masks/'+mask_style+'_'+grid+'.nc')
		pop_mask = np.array(nc_pop_mask.variables['mask'][:,:]).squeeze()
		pop_mask = np.roll(pop_mask,shift,axis=1)

		return pop_mask

	def grid_polygon_overlap(self,grid,lon,lat,grid_polygons,country_polygons,shift,mask_style,ext_poly,name,pop_mask=None):
		nx = len(lon)	;	ny = len(lat)

		overlap = np.zeros((ny,nx))
		for i in range(nx):
			for j in range(ny):
				# check gridcell is relevant
				if grid_polygons[i,j].intersects(ext_poly):
					# get fraction of grid-cell covered by polygon
					intersect = grid_polygons[i,j].intersection(country_polygons).area/grid_polygons[i,j].area*country_polygons.area
					if pop_mask!=None:
						# population weighting
						overlap[j,i] = intersect*pop_mask[j,i]
					if mask_style=='lat_weighted':
						# multiply overlap with latitude weighting
						overlap[j,i] = intersect*np.cos(np.radians(lat[j]))

		# renormalize overlap to get sum(mask)=1
		overlap_zwi=overlap.copy()
		overlap_sum=sum(overlap_zwi.flatten())
		if overlap_sum!=0:
			output=np.zeros(overlap.shape)
			output=overlap/overlap_sum
			# mask zeros
			output[output==0]=np.nan
			output=np.ma.masked_invalid(output)
			# shift back to original longitudes
			self._masks[grid][mask_style][name]=np.roll(output,shift,axis=1)		

	def create_mask_country(self,input_file,var_name,shape_file,mask_style='lat_weighted',pop_mask_file='',overwrite=False,lat_name='lat',lon_name='lon'):
		'''
		create country mask
		input_file: str: location of example input data (required for the identification of the grid)
		var_name: str: variable name of input file
		shape_file: str: location of the shape_file used to identify country borders
		mask_style: str: name under which the mask will be stored (important for further analysis)
		pop_mask_file: str: location of population mask (netcdf file) used for population weighted country mask
		'''

		lon,lat,grid,lon_shift = self.identify_grid(input_file,lat_name,lon_name)

		if grid not in self._masks.keys():
			self._masks[grid]={}
		if mask_style not in self._masks[grid].keys():
			self._masks[grid][mask_style]={}

		mask_file=self._working_directory+'/masks/'+self._iso+'_'+grid+'_'+mask_style+'.nc4'

		if os.path.isfile(mask_file) and overwrite==False:
 			self.load_masks(mask_file)

		else:
			grid_polygons,shift = self.get_grid_polygons(grid,lon,lat,lon_shift)
			
			# load shape file
			m = Basemap()
			m.readshapefile(shape_file, 'admin', drawbounds=False)

			# collect all shapes of country
			for shape, country in zip(m.admin, m.admin_info):
				country = {k.lower():v for k,v in country.items()}	
				if (country['iso_a3']==self._iso) | (country['adm0_a3']==self._iso):
					if 'country_polygons' in locals():
						country_polygons = \
						country_polygons.symmetric_difference(Polygon(shape))
					else:
						country_polygons = Polygon(shape)

			# get boundaries for faster computation
			xmin, xmax, ymin, ymax = country_polygons.bounds
			ext = [(xmin,ymin),(xmin,ymax),(xmax,ymax),(xmax,ymin),(xmin,ymin)]
			ext_poly = Polygon(ext)

			# load population mask		
			if pop_mask_file=='':	
				pop_mask = np.ones((len(lat),len(lon)))
			else:
				pop_mask = self.regrid_pop_mask(grid,lon,lat,shift,pop_mask_file,mask_style)

			# compute overlap
			self.grid_polygon_overlap(grid,lon, lat, grid_polygons, country_polygons, shift, mask_style, ext_poly, self._iso, pop_mask)

			# save mask
			print mask_file
			os.system('rm '+mask_file)
			nc_mask=Dataset(mask_file,'w')
			nc_mask.createDimension('lat', len(lat))
			nc_mask.createDimension('lon', len(lon))
 			outVar = nc_mask.createVariable('lat', 'f', ('lat',)) ; outVar[:]=lat[:]	;	outVar.setncattr('units','deg south')
 			outVar = nc_mask.createVariable('lon', 'f', ('lon',)) ; outVar[:]=lon[:]	;	outVar.setncattr('units','deg east')
 			outVar = nc_mask.createVariable(self._iso, 'f', ('lat','lon',),fill_value='NaN') ; outVar[:]=self._masks[grid][mask_style][self._iso][:,:]

			nc_mask.setncattr('original_grid',grid)
			nc_mask.setncattr('mask_style',mask_style)
			nc_mask.close()

	def create_mask_admin(self,input_file,var_name,shape_file,mask_style='lat_weighted',pop_mask_file='',overwrite=False,lat_name='lat',lon_name='lon'):
		'''
		create country mask
		input_file: str: location of example input data (required for the identification of the grid)
		var_name: str: variable name of input file
		shape_file: str: location of the shape_file used to identify country borders
		mask_style: str: name under which the mask will be stored (important for further analysis)
		pop_mask_file: str: location of population mask (netcdf file) used for population weighted country mask
		'''

		lon,lat,grid,lon_shift = self.identify_grid(input_file,lat_name,lon_name)

		if grid not in self._masks.keys():
			self._masks[grid]={}
		if mask_style not in self._masks[grid].keys():
			self._masks[grid][mask_style]={}

		mask_file=self._working_directory+'/masks/'+self._iso+'_admin_'+grid+'_'+mask_style+'.nc4'

		if os.path.isfile(mask_file) and overwrite==False:
 			self.load_masks(mask_file)

		else:
			grid_polygons,shift = self.get_grid_polygons(grid,lon,lat,lon_shift)
			
			# dopy shape file
			os.system('cp '+shape_file+'* '+self._working_directory+'/masks/')

			# load shape file
			m = Basemap()
			m.readshapefile(shape_file, 'admin', drawbounds=False)

			# collect all shapes of region
			region_polygons={}
			count=0			
			for shape, region in zip(m.admin, m.admin_info):
				region = {k.lower():v for k,v in region.items()}	
				name = region['name_1']
				if name in region_polygons.keys():
					region_polygons[name] = \
					region_polygons[name].symmetric_difference(Polygon(shape))
				else:
					region_polygons[name] = Polygon(shape)


			# get boundaries for faster computation
			xmins, xmaxs, ymins, ymaxs = [], [], [], []
			for name in region_polygons.keys():
				bounds=region_polygons[name].bounds
				xmins.append(bounds[0])
				xmaxs.append(bounds[1])
				ymins.append(bounds[2])
				ymaxs.append(bounds[3])
			xmin, xmax, ymin, ymax = min(xmins), max(xmaxs), min(ymins), max(ymaxs)
			ext = [(xmin,ymin),(xmin,ymax),(xmax,ymax),(xmax,ymin),(xmin,ymin)]
			ext_poly = Polygon(ext)

			# load population mask		
			if pop_mask_file=='':	
				pop_mask = np.ones((len(lat),len(lon)))
			else:
				pop_mask = self.regrid_pop_mask(grid,lon,lat,shift,pop_mask_file,mask_style)

			# prepare outputfile
			os.system('rm '+mask_file)
			nc_mask=Dataset(mask_file,'w')
			nc_mask.createDimension('lat', len(lat))
			nc_mask.createDimension('lon', len(lon))
 			outVar = nc_mask.createVariable('lat', 'f', ('lat',)) ; outVar[:]=lat[:]	;	outVar.setncattr('units','deg south')
 			outVar = nc_mask.createVariable('lon', 'f', ('lon',)) ; outVar[:]=lon[:]	;	outVar.setncattr('units','deg east')

			for name in region_polygons.keys():
				print name
				region_shape = region_polygons[name]
				self.grid_polygon_overlap(grid,lon, lat, grid_polygons, region_shape, shift, mask_style, ext_poly, name, pop_mask)
				outVar = nc_mask.createVariable(name, 'f', ('lat','lon',),fill_value='NaN') ; outVar[:]=self._masks[grid][mask_style][name][:,:]

			nc_mask.setncattr('original_grid',grid)
			nc_mask.setncattr('mask_style',mask_style)
			nc_mask.close()

	###########
	# raw data treatment
	###########

	def understand_time_format(self,nc_in=None,time=None,time_units=None,time_calendar=None):
		if time==None:
			time=nc_in.variables['time'][:]
		time=np.delete(time,np.where(time<0))

		datevar = []
		# if specified units and calendar
		if time_units!=None and time_calendar!=None:
			datevar.append(num2date(time,units = time_units,calendar= time_calendar))
		# if no specification
		if time_units==None and time_calendar==None:
			time_unit=nc_in.variables['time'].units
			try:	
				cal_temps = nc_in.variables['time'].calendar
				datevar.append(num2date(time,units = time_unit,calendar = cal_temps))
			except:
				datevar.append(num2date(time,units = time_unit))
		# create index variable
		year=np.array([int(str(date).split("-")[0])	for date in datevar[0][:]])
		month=np.array([int(str(date).split("-")[1])	for date in datevar[0][:]])
		day=np.array([int(str(date).split("-")[2].split(' ')[0])	for date in datevar[0][:]])

		return(time,year,month,day)

	def fill_gaps_in_time_axis(self,data_object,in_file,out_file):
			# write additional information in copied file
			nc_in=Dataset(in_file,"r")
			os.system('rm '+out_file)
			nc_out=Dataset(out_file,"w")
			raw_data=nc_in.variables[data_object.original_var_name][:,:,:]

			# understand time format and create continuous time axis
			time,year,month,day=self.understand_time_format(nc_in)
			data_object.add_data(time=time,year=year,month=month,day=day)
			data_object.create_time_stamp()	

			time_axis=np.around(np.arange(np.nanmin(data_object.time_stamp),np.nanmax(data_object.time_stamp),data_object.time_step),decimals=4)
			out_data=np.zeros([len(time_axis),len(data_object.lat),len(data_object.lon)])*np.nan
			for t in time_axis:
				if t in data_object.time_stamp:
					# some files have more than one value per time step????
					#print t,time_axis[np.where(time_axis==t)[0]],data_object.time_stamp[np.where(data_object.time_stamp==t)[0]]
					out_data[np.where(time_axis==t)[0][0],:,:]=raw_data[np.where(data_object.time_stamp==t)[0][0],:,:]

			data_object.time_stamp=time_axis
			data_object.convert_time_stamp()
			data_object.add_data(raw=out_data)

			nc_out.createDimension('lat', len(data_object.lat))
			nc_out.createDimension('lon', len(data_object.lon))
			nc_out.createDimension('time', len(time_axis))

			varin=nc_in.variables['lat']
			outVar = nc_out.createVariable('lat', varin.datatype, varin.dimensions)
			outVar.setncatts({k: varin.getncattr(k) for k in varin.ncattrs()})
			outVar[:] = varin[:]

			varin=nc_in.variables['lon']
			outVar = nc_out.createVariable('lon', varin.datatype, varin.dimensions)
			outVar.setncatts({k: varin.getncattr(k) for k in varin.ncattrs()})
			outVar[:] = varin[:]

 			outVar = nc_out.createVariable('time', 'f', ('time',)) ; outVar[:]=data_object.time
 			outVar.setncatts({'calendar':'proleptic_gregorian','units':'days since 1950-1-1 00:00:00'})

 			print len(data_object.year)
 			print len(data_object.month)
 			print len(data_object.day)

 			outVar = nc_out.createVariable('year', 'f', ('time',)) ; outVar[:]=data_object.year
 			outVar = nc_out.createVariable('month', 'f', ('time',)) ; outVar[:]=data_object.month
 			outVar = nc_out.createVariable('day', 'f', ('time',)) ; outVar[:]=data_object.day

			varin=nc_in.variables[data_object.original_var_name]
			outVar = nc_out.createVariable(data_object.original_var_name, varin.datatype, varin.dimensions)
			outVar.setncatts({k: varin.getncattr(k) for k in varin.ncattrs()})
			outVar[:] = out_data

 			nc_out.setncattr('original_grid',data_object.grid)
 			nc_out.setncattr('tags_keys','**'.join(data_object.all_tags_dict.keys()))
 			nc_out.setncattr('tags_values','**'.join(data_object.all_tags_dict.values()))

			nc_out.close()
			nc_in.close()
			os.system('rm '+in_file)

	def country_zoom(self,input_file,var_name,mask_style='lat_weighted',time_units=None,time_calendar=None,lat_name='lat',lon_name='lon',overwrite=False,**kwargs):
		'''
		zoom input_file to area relevant for the country
		input_file: type str: file to be processed
		out_file: type str: filepath where output is going to be stored
		var: type str: variable name in netcdf file
		iso: type str: iso3c of country
		mask_path: type str: path to where the masks are stored
		'''

		print kwargs
		out_file=self._working_directory+'/raw/'+input_file.split('/')[-1].replace('.nc','_'+self._iso+'.nc')

		if os.path.isfile(out_file) and overwrite==False:
			nc_out=Dataset(out_file,"r")

			new_data=new_data_object(outer_self=self,var_name=var_name,raw_file=out_file,grid=nc_out.getncattr('original_grid'),**kwargs)
			new_data.add_data(raw=nc_out.variables[var_name][:,:,:],lat=nc_out.variables['lat'][:],lon=nc_out.variables['lon'][:],time=nc_out.variables['time'][:],year=nc_out.variables['year'][:],month=nc_out.variables['month'][:])
			new_data.create_time_stamp()
			nc_out.close()


		else:
			# open file to get information
			print input_file
			lon_in,lat_in,grid,lon_shift = self.identify_grid(input_file,lat_name,lon_name)


			country_mask=self._masks[grid][mask_style][self._iso]
			lat_mask=self._masks[grid]['lat_mask']
			lon_mask=self._masks[grid]['lon_mask']

			# find relevant area (as rectangle)
			lon_mean=np.mean(country_mask,0)
			lons=sorted(np.where(lon_mean!=0)[0])

			lat_mean=np.mean(country_mask,1)
			lats=sorted(np.where(lat_mean!=0)[0])

			nx,ny=len(lons),len(lats)

			lon=lon_mask[list(lons)]
			lat=lat_mask[list(lats)]

			# zoom to relevant area
			os.system('cdo -O sellonlatbox,'+str(min(lon))+','+str(max(lon))+','+str(min(lat))+','+str(max(lat))+' '+input_file+' '+out_file.replace('.nc','_tmp.nc'))

			new_data=new_data_object(outer_self=self,var_name=var_name,raw_file=out_file,grid=grid,**kwargs)
			new_data.raw_file=out_file
			new_data.add_data(lon=lon,lat=lat)
			self.fill_gaps_in_time_axis(new_data,out_file.replace('.nc','_tmp.nc'),out_file)

	def hist_merge(self):
		# why are there files missing if I go through self._DATA only once???
		for data in self._DATA+self._DATA:
			if hasattr(data,'model'):
				data__=self.selection([data.model,data.var_name,data.data_type],show_selection=True)
				for hist in data__[:]:
					if hist.scenario.lower() in ['hist','historical']:
						delete_hist=False
						print '------- merging ',hist.model,hist.var_name,'-----------'
						print ' '.join([d_d.raw_file for d_d in data__])

						for ddd in data__[:]:	
							if ddd.scenario.lower() not in ['hist','historical']:
								out_file = ddd.raw_file.replace('.nc','_merged.nc')
								tmp_file = ddd.raw_file.replace('.nc','_merged_tmp.nc')

								os.system('cdo -O mergetime '+ddd.raw_file+' '+hist.raw_file+' '+tmp_file)
								os.system('rm '+ddd.raw_file)

								ddd.raw_file=out_file
								self.fill_gaps_in_time_axis(ddd,tmp_file,out_file)

								delete_hist=True

						if delete_hist:	
							self._DATA.remove(hist)
							os.system('rm '+hist.raw_file)

	def ensemble_mean(self):
		# why do I need this????? see hist_merge
		for i in range(2):
			remaining=self._DATA[:]
			for data in remaining:
				if hasattr(data,'model'):
					if data.model!='ensemble_mean':
						print '---------------- ensemble mean',data.var_name,'--------------------'
						ensemble,ensemble_mean=self.find_ensemble([data.data_type,data.var_name,data.scenario])
						if ensemble_mean==None:
							print 'ooooo'
							ensemble=ensemble.values()
							
							time_min,time_max=[],[]
							for member in ensemble:
								remaining.remove(member)
								time_min.append(min(member.time_stamp))
								time_max.append(max(member.time_stamp))
							time_axis=np.around(np.arange(max(time_min),min(time_max),member.time_step),decimals=4)	
							ensemble_mean=np.zeros([len(ensemble),len(time_axis),len(member.lat),len(member.lon)])*np.nan

							for member,i in zip(ensemble,range(len(ensemble))):
								for t in member.time_stamp:
									#print t,np.where(time_axis==t)[0],np.where(member.time_stamp==t)[0]
									ensemble_mean[i,np.where(time_axis==t)[0],:,:]=member.raw[np.where(member.time_stamp==t)[0],:,:]													

							ensemble_mean=np.nanmean(ensemble_mean,axis=0)

							tags_=ensemble[0].all_tags_dict.copy()
							tags_['model']='ensemble_mean'
							out_file=self._working_directory+'/raw/'+ensemble[0].var_name+'_'+ensemble[0].data_type+'_ensemble-mean_'+ensemble[0].scenario+'.nc'
							tags_['raw_file']=out_file

							new_data=new_data_object(outer_self=self,**tags_)
							new_data.add_data(raw=ensemble_mean,lat=member.lat,lon=member.lon)

							new_data.time_stamp=time_axis
							new_data.convert_time_stamp()

							# write ensemble_mean to file
							print member.raw_file
							nc_in=Dataset(member.raw_file,"r")
							os.system('rm '+out_file)
							nc_out=Dataset(out_file,"w")

							nc_out.createDimension('lat', len(new_data.lat))
							nc_out.createDimension('lon', len(new_data.lon))
							nc_out.createDimension('time', len(time_axis))

							varin=nc_in.variables['lat']
							outVar = nc_out.createVariable('lat', varin.datatype, varin.dimensions)
							outVar.setncatts({k: varin.getncattr(k) for k in varin.ncattrs()})
							outVar[:] = varin[:]

							varin=nc_in.variables['lon']
							outVar = nc_out.createVariable('lon', varin.datatype, varin.dimensions)
							outVar.setncatts({k: varin.getncattr(k) for k in varin.ncattrs()})
							outVar[:] = varin[:]

				 			outVar = nc_out.createVariable('time', 'f', ('time',)) ; outVar[:]=new_data.time
				 			outVar.setncatts({'calendar':'proleptic_gregorian','units':'days since 1950-1-1 00:00:00'})

				 			outVar = nc_out.createVariable('year', 'f', ('time',)) ; outVar[:]=new_data.year
				 			outVar = nc_out.createVariable('month', 'f', ('time',)) ; outVar[:]=new_data.month
 							outVar = nc_out.createVariable('day', 'f', ('time',)) ; outVar[:]=new_data.day

							varin=nc_in.variables[new_data.original_var_name]
							outVar = nc_out.createVariable(new_data.original_var_name, varin.datatype, varin.dimensions)
							outVar.setncatts({k: varin.getncattr(k) for k in varin.ncattrs()})
							outVar[:] = ensemble_mean[:,:,:]

				 			nc_out.setncattr('original_grid',new_data.grid)
				 			nc_out.setncattr('tags_keys','**'.join(new_data.all_tags_dict.keys()))
				 			nc_out.setncattr('tags_values','**'.join(new_data.all_tags_dict.values()))

							nc_out.close()
							nc_in.close()

	###########
	# analysis tools
	###########

	def area_average(self,mask_style='lat_weighted',filters=[],overwrite=False):
		'''
		compute countrywide averages for all loaded datasets
		mask_style: str: weighting used to compute countrywide averages
		filters: list of strs: only computed for data which have the tags given in filters
		'''

		for data in self._DATA:
			compute=True
			for key in filters:
				if key not in data.all_tags:
					compute=False

			if compute:
				# check if file has been saved
				out_file=self._working_directory+'/area_average/country_mean-'+data.name+'-'+mask_style+'.csv'
				if mask_style not in data.area_average.keys():	data.area_average[mask_style]={}
				data.area_average[mask_style]['out_file']=out_file

				if os.path.isfile(out_file) and overwrite==False:
					table=pd.read_csv(out_file,sep=';')
					for key in table.keys():
						if key not in ['time','year','month']:
							data.area_average[mask_style][key]=np.array(table[key])

				else:
					# prepare table
					country_mean_csv = pd.DataFrame(index=range(len(data.time)))
					country_mean_csv['time']=data.time
					country_mean_csv['month']=data.month
					country_mean_csv['year']=data.year
					country_mean_csv['day']=data.day

					# load input data
					var_in=data.raw.copy()			
					try:	# handle masked array
						masked=np.ma.getmask(var_in)
						var_in=np.ma.getdata(var_in)
						var_in[masked]=np.nan
					except: pass

					# find relevant area (as rectangle) and check whether lon and lat are correct (on same grid differences in lat decreasing or increasing could arise)
					mask=self._masks[data.grid][mask_style][self._iso]
					lat_mask=self._masks[data.grid]['lat_mask']
					lon_mask=self._masks[data.grid]['lon_mask']

					lat_mean=np.mean(mask,1)
					lats=np.where(lat_mean!=0)
					if lat_mask[lats][0]!=data.lat[0]:
						var_in=var_in[:,:,::-1]
						if lat_mask[lats][0]!=data.lat[-1]:
							print 'problem with lat' ; return('error')

					lon_mean=np.mean(mask,0)
					lons=np.where(lon_mean!=0)
					if lon_mask[lons][0]!=data.lon[0]:
						var_in=var_in[:,:,::-1]
						if lon_mask[lons][0]!=data.lon[-1]:
							print 'problem with lon' ; return('error')

					# get mask
					for name in self._masks[data.grid][mask_style].keys():
						mask=self._masks[data.grid][mask_style][name]

						# zoom mask to relevant area
						mask=mask[np.ix_(list(lats[0]),list(lons[0]))]
						country_area=np.where(mask>0)

						data.area_average[mask_style][name]=data.time.copy()*np.nan
						for i in range(len(data.time)):
							var_of_area=var_in[i,:,:][country_area]
							# NA handling: sum(mask*var)/sum(mask) for the area where var is not NA
							not_missing_in_var=np.where(np.isfinite(var_of_area))[0]	# np.where()[0] because of array([],)
							if len(not_missing_in_var)>0:
								data.area_average[mask_style][name][i]=sum(mask[country_area][not_missing_in_var]*var_of_area[not_missing_in_var])/sum(mask[country_area][not_missing_in_var])
				

						country_mean_csv[name]=data.area_average[mask_style][name]


					# save as csv 
					country_mean_csv.to_csv(out_file,na_rep='NaN',sep=';',index_label='index',encoding='utf-8')

	def period_statistics(self,name='mean',threshold=None,below=False,selection=None,periods={'ref':[1986,2006],'2030s':[2025,2045],'2040s':[2035,2055]}):
		'''
		computes time averages for each grid-cell for a given period
		periods: dict={'period_name':[start_year,end_year], ...}: start and end years of period
		filters: list of strs: only computed for data which have the tags given in filters
		'''

		if selection==None:
			selection=self._DATA

		for data in selection:
			compute=True
			if 'ensemble_mean' in data.all_tags:
				compute=False

			# handle warming slices and fixed periods
			if depth(periods)==2:		
				local_periods=periods
			if depth(periods)>2:		
				try:	local_periods=periods[data.model][data.scenario]
				except:	compute=False

			if compute:
				if hasattr(data,'period')==False:	data.period={}
				if name not in data.period.keys(): data.period[name]={}

				if data.time_format=='monthly':		seasons=self._seasons
				if data.time_format=='10day':		seasons=self._seasons
				if data.time_format=='yearly':		seasons={'year':range(1,13)}

				if isinstance(threshold, (float,int)) and threshold!=None: 
					threshold=np.ones([data.raw.shape])*threshold

				if isinstance(threshold, (dict)) and threshold!=None: 
					threshold_new=data.raw.copy()*np.nan 
					for tt,i in zip(data.time_in_year,range(len(data.time_in_year))):
						threshold_new[i,:,:]=threshold[tt-int(tt)]
					threshold=threshold_new


				for period_name,period in zip(local_periods.keys(),local_periods.values()):	
					for mons_in_sea,sea in zip(seasons.values(),seasons.keys()):
						if sea not in data.period[name].keys(): data.period[name][sea]={}
						# find relevant time steps
						relevant_years=np.where((data.year>=period[0]) & (data.year<period[1]))[0]
						relevenat_time_steps=data.get_relevant_time_steps_in_season(mons_in_sea,relevant_years)

						n_steps=len(relevenat_time_steps)
						if n_steps>0:
							# compute average
							if name=='mean':
								data.period[name][sea][period_name]=np.nanmean(data.raw[relevenat_time_steps,:,:],axis=0)
							# threshold exceeding
							if threshold!=None:
								# sub_thresh=np.zeros([data.raw.shape[1],data.raw.shape[2]])*np.nan
								# for tt,i in zip(data.time_in_year,range(len(data.time_in_year))):
								# 	data.period[name][sea][period_name][i,:,:]=data.raw[i,:,:]-thresh[tt-int(tt)]
								# sub_thresh[sub_thresh>0]=1
								# sub_thresh[sub_thresh<0]=-1
								data.period[name][sea][period_name]=np.zeros([data.raw.shape[1],data.raw.shape[2]])*np.nan
								for y in range(data.raw.shape[1]):
									for x in range(data.raw.shape[2]):
										if below==True: 
											data.period[name][sea][period_name][y,x]=len(np.where(data.raw[relevenat_time_steps,y,x]<threshold[relevenat_time_steps,y,x])[0])/float(n_steps)
										if below==False: 
											data.period[name][sea][period_name][y,x]=len(np.where(data.raw[relevenat_time_steps,y,x]>threshold[relevenat_time_steps,y,x])[0])/float(n_steps)
						else: 
							print 'years missing for',period_name,'in',data.name
							data.period[name][sea][period_name]=np.zeros([data.raw.shape[1],data.raw.shape[2]])*np.nan
						print period_name,sea
						print threshold[1:10,:,:]
						print data.period[name][sea][period_name]

				# period diff
				for sea in data.period[name].keys():
					for period_name in data.period[name][sea].keys():	
						if period_name!='ref' and 'ref' in data.period[name][sea].keys():
							data.period[name][sea]['diff_'+period_name+'-'+'ref']=data.period[name][sea][period_name]-data.period[name][sea]['ref']
							data.period[name][sea]['diff_relative_'+period_name+'-'+'ref']=(data.period[name][sea][period_name]-data.period[name][sea]['ref'])/data.period[name][sea]['ref']*100

	def period_model_agreement(self,filters=[]):
		'''
		computes time averages for each grid-cell for a given period
		filters: list of strs: only computed for data which have the tags given in filters
		'''
		remaining=self._DATA[:]

		for data in remaining:
			compute=False
			if hasattr(data,'model'):
				if data.model!='ensemble_mean':
					compute=True
					for key in filters:
						if key not in data.all_tags:
							compute=False

			if compute:
				ensemble,ensemble_mean=self.find_ensemble([data.data_type,data.var_name,data.scenario])
				ensemble=ensemble.values()
				if hasattr(ensemble_mean,'period')==False:	ensemble_mean.period={}
				if hasattr(ensemble_mean,'agreement')==False:	ensemble_mean.agreement={}

				for member in ensemble:
					remaining.remove(member)

				if hasattr(member,'period'):
					if member.time_format=='monthly':		seasons=self._seasons
					if member.time_format=='10day':		seasons=self._seasons
					if member.time_format=='yearly':		seasons={'year':range(1,13)}

					for name in ensemble[0].period.keys():
						ensemble_mean.period[name]={}
						ensemble_mean.agreement[name]={}
						for sea in seasons.keys():
							ensemble_mean.period[name][sea]={}
							ensemble_mean.agreement[name][sea]={}

							# ensemble mean
							for period in ensemble[0].period[name][sea].keys():
								ensemble_mean.period[name][sea][period]=ensemble[0].period[name][sea][period]
								for member in ensemble[1:]:
									ensemble_mean.period[name][sea][period]+=member.period[name][sea][period]
								ensemble_mean.period[name][sea][period]/=float(len(ensemble))

							# model agreement
							for period in ensemble_mean.period[name][sea].keys():
								if len(period.split('-'))>1 and period.split('-')[-1]=='ref':
									agreement=ensemble_mean.period[name][sea][period].copy()*0
									for member in ensemble:
										agreement+=np.sign(member.period[name][sea][period])==np.sign(ensemble_mean.period[name][sea][period])

									agreement[agreement<2./3.*len(ensemble)]=0
									agreement[agreement>=2./3.*len(ensemble)]=1
									ensemble_mean.agreement[name][sea][period]=agreement

	def annual_cycle(self,periods={'ref':[1986,2006],'2030s':[2025,2045],'2040s':[2035,2055]},mask_style='lat_weighted',selection=None):
		'''
		computes time averages for each grid-cell for a given period
		periods: dict={'period_name':[start_year,end_year], ...}: start and end years of period
		filters: list of strs: only computed for data which have the tags given in filters
		'''

		if selection==None:
			selection=self._DATA

		for data in selection:
			compute=True
			if 'ensemble_mean' in data.all_tags:
				compute=False

			# handle warming slices and fixed periods
			if depth(periods)==2:		
				local_periods=periods
			if depth(periods)>2:		
				try:	local_periods=periods[data.model][data.scenario]
				except:	compute=False

			if compute:
				print data.name
				data.steps_in_year=sorted(set(np.around(data.time_stamp-data.year,decimals=4)))
				if hasattr(data,'annual_cycle')==False:	data.annual_cycle={}
				if mask_style not in data.annual_cycle.keys():		data.annual_cycle[mask_style]={}
				#data.annual_cycle={key : val for key,val in zip(local_periods.keys(),local_periods.values())}

				for region in self._regions.keys():
					if region not in data.annual_cycle[mask_style].keys():		
						data.annual_cycle[mask_style][region]={}
					for period_name,period in zip(local_periods.keys(),local_periods.values()):	
						annual_cycle=[]
						for time_in_year in data.steps_in_year:
							relevant_time=np.where((data.year>=period[0]) & (data.year<period[1]) & (np.around(data.time_stamp-data.year,decimals=4)==time_in_year))[0]
							if len(relevant_time)>1:
								annual_cycle.append(np.nanmean(data.area_average[mask_style][region][relevant_time]))
						if len(annual_cycle)==len(data.steps_in_year):
							data.annual_cycle[mask_style][region][period_name]=np.array(annual_cycle)
						else:
							data.annual_cycle[mask_style][region][period_name]=np.zeros([len(data.steps_in_year)])*np.nan
						
						# annual cycle diff
						for period_name in data.annual_cycle[mask_style][region].keys():	
							if period_name!='ref' and 'ref' in data.annual_cycle[mask_style][region].keys():
								data.annual_cycle[mask_style][region]['diff_'+period_name+'-'+'ref']=data.annual_cycle[mask_style][region][period_name]-data.annual_cycle[mask_style][region]['ref']
								data.annual_cycle[mask_style][region]['diff_relative_'+period_name+'-'+'ref']=(data.annual_cycle[mask_style][region][period_name]-data.annual_cycle[mask_style][region]['ref'])/data.annual_cycle[mask_style][region]['ref']*100

	def annual_cycle_ensemble_mean(self,filters=[]):
		'''
		computes time averages for each grid-cell for a given period
		filters: list of strs: only computed for data which have the tags given in filters
		'''
		remaining=self._DATA[:]

		for data in remaining:
			compute=False
			if hasattr(data,'model'):
				if data.model!='ensemble_mean':
					compute=True
					for key in filters:
						if key not in data.all_tags:
							compute=False

			if compute:
				ensemble,ensemble_mean=self.find_ensemble([data.data_type,data.var_name,data.scenario])
				ensemble=ensemble.values()

				ensemble_mean.steps_in_year=sorted(set(np.around(ensemble_mean.time_stamp-ensemble_mean.year,decimals=4)))

				for member in ensemble:
					remaining.remove(member)

				# annual cycle ensemble mean
				if hasattr(member,'annual_cycle'):
					if hasattr(ensemble_mean,'annual_cycle')==False:			ensemble_mean.annual_cycle={}
					for mask_style in ensemble[0].annual_cycle.keys():
						if mask_style not in ensemble_mean.annual_cycle.keys():		ensemble_mean.annual_cycle[mask_style]={}
						for region in self._regions.keys():
							ensemble_mean.annual_cycle[mask_style][region]={}
							for period in ensemble[0].annual_cycle[mask_style][region].keys():
								ensemble_mean.annual_cycle[mask_style][region][period]=np.nanmean(np.vstack([member.annual_cycle[mask_style][region][period] for member in ensemble]),axis=0)


	###########
	# plot functions
	###########

	def display_mask(self,grid=None,mask_style=None):
		if grid==None:
			print 'Please select a grid:'
			for grid in self._masks.keys():
				print grid
			return None
		if mask_style==None:
			print 'Please select a mask-style:'
			for key in self._masks[grid].keys():
				if key not in ['lat_mask','lon_mask']:
					print key
			return None

		else:
			toplo=self._masks[grid][mask_style][self._iso]
			lat=self._masks[grid]['lat_mask'].copy()
			lon=self._masks[grid]['lon_mask'].copy()

			plot_map(toplo,lat,lon,title=grid+' '+mask_style)			

	def get_adm_polygons(self):
		self._adm_polygons={}

		m = Basemap()
		m.readshapefile(self._working_directory+'/masks/'+self._iso+'_adm1', 'admin', drawbounds=False)

		count=0			
		for shape in m.admin:	
			x,y=Polygon(shape).exterior.xy
			self._adm_polygons[count]={'x':x,'y':y}
			count+=1

	def plot_map(self,to_plot,lat,lon,color_bar=True,color_label='',color_palette=plt.cm.plasma,color_range=None,grey_area=None,limits=None,ax=None,out_file=None,title='',polygons=None):
		# this actualy plots the map

			if ax==None: show=True
			if ax!=None: show=False

			if ax==None:
				fig, ax = plt.subplots(nrows=1, ncols=1,figsize=(5,3))		


			# handle limits
			if limits==None:
				half_lon_step=abs(np.diff(lon.copy(),1)[0]/2)
				half_lat_step=abs(np.diff(lat.copy(),1)[0]/2)
				relevant_lats=lat[np.where(np.isfinite(to_plot))[0]]
				relevant_lons=lon[np.where(np.isfinite(to_plot))[1]]
				limits=[np.min(relevant_lons)-half_lon_step,np.max(relevant_lons)+half_lon_step,np.min(relevant_lats)-half_lat_step,np.max(relevant_lats)+half_lat_step]


			# handle 0 to 360 lon
			if max(lon)>180:
				problem_start=np.where(lon>180)[0][0]
				new_order=np.array(range(problem_start,len(lon))+range(0,problem_start))
				to_plot=to_plot[:,new_order]
				lon=lon[new_order]
				lon[lon>180]-=360

			if limits[0]>180:limits[0]-=360
			if limits[1]>180:limits[1]-=360


			m = Basemap(ax=ax,llcrnrlon=limits[0],urcrnrlon=limits[1],llcrnrlat=limits[2],urcrnrlat=limits[3],resolution="l",projection='cyl')
			m.drawmapboundary(fill_color='1.')

			# get color_range
			if color_range==None:
				color_range=[np.min(to_plot[np.isfinite(to_plot)]),np.max(to_plot[np.isfinite(to_plot)])]

			x,y=lon.copy(),lat.copy()
			x-=np.diff(x,1)[0]/2.
			y-=np.diff(y,1)[0]/2.
			x=np.append(x,[x[-1]+np.diff(x,1)[0]])
			y=np.append(y,[y[-1]+np.diff(y,1)[0]])
			x,y=np.meshgrid(x,y)
			im = m.pcolormesh(x,y,to_plot,cmap=color_palette,vmin=color_range[0],vmax=color_range[1])


			# mask some grid-cells
			if grey_area!=None:
				to_plot=grey_area.copy()
				to_plot[to_plot==0]=0.5
				to_plot[to_plot==1]=np.nan
				to_plot=np.ma.masked_invalid(to_plot)
				im2 = m.pcolormesh(x,y,to_plot,cmap=plt.cm.Greys,vmin=0,vmax=1)

			# show coastlines and borders
			m.drawcoastlines()
			m.drawstates()
			m.drawcountries()

			# add polygons
			if polygons==None and hasattr(self,'_adm_polygons'):
				polygons=self._adm_polygons
				for index in polygons.keys():
					m.plot(polygons[index]['x'],polygons[index]['y'],color='black',linewidth=0.5)

			# add colorbar
			if color_bar==True:
				cb = m.colorbar(im,'right', size="5%", pad="2%")
				tick_locator = ticker.MaxNLocator(nbins=5)
				cb.locator = tick_locator
				cb.update_ticks()
				cb.set_label(color_label, rotation=90)

			ax.set_title(title.replace('_',' '))
			ax.legend(loc='best')


			if out_file==None and show==True:plt.show()
			if out_file!=None:plt.savefig(out_file)

			return(im,color_range)

class new_data_object(object):
	def __init__(SELF,outer_self,**kwargs):
		SELF.index=len(outer_self._DATA)
		SELF.outer_self=outer_self
		outer_self._DATA.append(SELF)
		SELF._iso=outer_self._iso

		if 'raw_file' in kwargs.keys():	SELF.raw_file=outer_self._working_directory+'/raw/'+kwargs['raw_file'].split('raw/')[-1]
		if 'grid' in kwargs.keys():	SELF.grid=kwargs['grid']
		if 'time_format' in kwargs.keys():	SELF.time_format=kwargs['time_format']

		SELF.original_var_name=kwargs['var_name']
		if 'given_var_name' in kwargs.keys():	SELF.var_name=kwargs['given_var_name']
		if 'given_var_name' not in kwargs.keys():	SELF.var_name=kwargs['var_name']

		if 'data_type' in kwargs.keys():	SELF.data_type=kwargs['data_type']
		if 'scenario' in kwargs.keys():	SELF.scenario=kwargs['scenario'].replace('.','p').lower()
		if 'model' in kwargs.keys():	SELF.model=kwargs['model']

		SELF.area_average={}

		SELF.all_tags_dict=kwargs
		SELF.all_tags_dict.pop('raw_file', None)
		SELF.all_tags=kwargs.values()
		if 'given_var_name' in kwargs.keys():	SELF.all_tags.remove(kwargs['var_name'])


		SELF.name=SELF.var_name
		for key in sorted(kwargs.keys()):
			if key not in ['raw_file','grid','var_name','given_var_name']:
				SELF.name+='_'+kwargs[key]

	# def duplicate(SELF,new_var_name):
	# 	SELF=SELF.copy()
	# 	SELF.outer_self._DATA.append(SELF)
	# 	SELF.var_name=new_var_name
	# 	SELF.all_tags_dict['given_var_name']=new_var_name

	# 	delattr(SELF,'raw')
	# 	delattr(SELF,'area_average')
	# 	delattr(SELF,'perio')
	# 	delattr(SELF,'annual_cycle')

	# 	return(SELF)

	def add_data(SELF,**kwargs):
		if 'raw' in kwargs.keys():	SELF.raw=kwargs['raw']
		if 'time' in kwargs.keys():	SELF.time=kwargs['time']
		if 'year' in kwargs.keys():	SELF.year=kwargs['year']
		if 'month' in kwargs.keys():	SELF.month=kwargs['month']
		if 'day' in kwargs.keys():	SELF.day=kwargs['day']
		if 'lat' in kwargs.keys():	SELF.lat=kwargs['lat']
		if 'lon' in kwargs.keys():	SELF.lon=kwargs['lon']

	def create_time_stamp(SELF):
		SELF.time_stamp=np.array([(datetime.datetime(SELF.year[i],SELF.month[i],SELF.day[i]) - datetime.datetime(1950,1,1)).days for i in range(len(SELF.year))])

		# if SELF.time_format=='yearly':
		# 	SELF.time_step=1
		# 	SELF.time_stamp=np.around([int(SELF.year[i]) for i in range(len(SELF.year))])
		# elif SELF.time_format=='monthly':
		# 	SELF.time_step=1./12.
		# 	SELF.time_stamp=np.around([int(SELF.year[i])+int(SELF.month[i])/12. for i in range(len(SELF.year))],decimals=4)
		# elif SELF.time_format=='10day':
		# 	SELF.time_step=1./36.
		# 	SELF.time_stamp=np.around([int(SELF.year[i])+((int(SELF.month[i])-1)*3.+round((int(SELF.day[i])-5)/10.))/36. for i in range(len(SELF.year))],decimals=4)

		# SELF.time_in_year = np.around(SELF.time_stamp-SELF.year,decimals=4)

	def convert_time_stamp(SELF):

		datevar.append(num2date(SELF.time,units = 'days since 1950-1-1 00:00:00'))
		year=np.array([int(str(date).split("-")[0])	for date in datevar[0][:]])
		month=np.array([int(str(date).split("-")[1])	for date in datevar[0][:]])
		day=np.array([int(str(date).split("-")[2].split(' ')[0])	for date in datevar[0][:]])


		# SELF.year=np.array([int(t) for t in SELF.time_stamp])
		# SELF.time_in_year = np.around(SELF.time_stamp-SELF.year,decimals=4)
		# SELF.month=np.array([int(round(t*12)) for t in SELF.time_in_year])

		# if SELF.time_format=='10day':
		# 	day=[]
		# 	for t in SELF.time_stamp:
		# 		yr=int(t)
		# 		mth=int((t-yr)*12+1)
		# 		dy=int((t-yr-(mth-1)/12.)*36)*10+5
		# 		day.append(dy)
		# 	SELF.day=np.array(day)

		# else:
		# 	SELF.day=SELF.year.copy()*0+15

		# print SELF.day[1:50]
		# print SELF.month[1:50]
		# print SELF.year[1:50]
		# print len(SELF.day),len(SELF.month),len(SELF.year)
		# SELF.time=np.array([(datetime.datetime(SELF.year[i],SELF.month[i],SELF.day[i]) - datetime.datetime(1950,1,1)).days for i in range(len(SELF.year))])

	def get_relevant_time_steps_in_season(SELF,months_in_season,relevant_years=None):
		if relevant_years==None:
			relevant_years=range(len(SELF.year))
		relevenat_time_steps=[]
		for yr in relevant_years:
			if int(SELF.month[yr]) in months_in_season:
				relevenat_time_steps.append(yr)
		return(relevenat_time_steps)		

	def display_map(SELF,period=None,name='mean',time=None,color_bar=True,color_label=None,color_palette=None,color_range=None,grey_area=None,limits=None,ax=None,out_file=None,title=None,polygons=None,season='year'):
		'''
		plot maps of data. 
		meta_data: list of strs: meta information required to acces data
		source: str: default='_data'. if masks are to be plotted, specify source='_masks'
		period: str: if  the averag over a period is to be plotted specify the period name
		time: int: index in time axis of data (to be plotted)
		color_bar: logical: if True, color-scale is plotted besides the map
		color_label: str: label of the color-scale
		color_palette: plt.cm. object: colors used
		color_range: [float,float]: minimal and maximal value on color-scale
		limits: [lon_min,lon_max,lat_min,lat_max]: extend of the map
		ax: subplot: subplot on which the map will be plotted
		out_file: str: location where the plot is saved
		title: str: title of the plot
		show: logical: show the subplot?
		'''

		# this prepares plotting

		if period==None:
			if time==None:
				time=int(len(SELF.time)/2)
				print 'no time specified. '+str(int(SELF.month[time]))+'/'+str(int(SELF.year[time]))+' selected'
				to_plot=SELF.raw[time,:,:].copy()
				if title==None:title='_'.join([SELF.name]+[str(int(SELF.month[time])),'/',str(int(SELF.year[time]))])
		else:
			to_plot=SELF.period[name][season][period].copy()
			if title==None:title=SELF.name+'_'+name+'_'+period+'_'+season

			if hasattr(SELF,'agreement'):
				print 'agreement exists'
				if period in SELF.agreement[name][season].keys():
					print 'also for the period'
					grey_area=SELF.agreement[name][season][period]

		if len(np.where(np.isfinite(to_plot)==False)[0])==len(to_plot.flatten()):
			print 'nothing to plot here'
			return(None,None)

		lat=SELF.lat.copy()
		lon=SELF.lon.copy()
		if color_label==None:color_label=SELF.var_name.replace('_',' ')

		if color_range==None:
			if period.split('_')[0]=='diff':
				if np.sign(np.nanpercentile(to_plot,[10]))==np.sign(np.nanpercentile(to_plot,[90])):
					color_range=np.nanpercentile(to_plot,[10,90])
				else:
					abs_boundary=max(abs(np.nanpercentile(to_plot,[10,90])))
					color_range=[-abs_boundary,abs_boundary]

		if color_palette==None:
			if period.split('_')[0]!='diff':
				if SELF.var_name in ['pr','RX1','year_RX5']:	color_palette=plt.cm.YlGnBu
				elif SELF.var_name in ['tas','TXx']:			color_palette=plt.cm.OrRd
				elif SELF.var_name in ['SPEI','year_CDD']:		color_palette=plt.cm.YlOrBr
				else:											color_palette=plt.cm.plasma

			if period.split('_')[0]=='diff': 
				if np.mean(color_range)==0:						color_palette=plt.cm.PiYG_r
				elif np.mean(color_range)<0:					color_palette=plt.cm.YlGn_r
				elif np.mean(color_range)>0:					color_palette=plt.cm.RdPu

		im,color_range=SELF.outer_self.plot_map(to_plot,lat,lon,color_bar=color_bar,color_label=color_label,color_palette=color_palette,color_range=color_range,grey_area=grey_area,limits=limits,ax=ax,out_file=out_file,title=title,polygons=polygons)
		return(im,color_range)

	def plot_transients(SELF,mask_style='lat_weighted',season='year',region=None,running_mean_years=1,ax=None,out_file=None,title=None,ylabel=None,label='',color='blue',y_range=None):
		'''
		plot transient of countrywide average
		mask_style: str: weighting used to compute countrywide averages
		running_mean: int: years to be averaged in moving average		
		ax: subplot: subplot on which the map will be plotted
		out_file: str: location where the plot is saved
		title: str: title of the plot
		ylabel: str: labe to put on y-axis
		show: logical: show the subplot?
		'''

		if ax!=None:
			show=False

		if ax==None:
			show=True
			fig, ax = plt.subplots(nrows=1, ncols=1,figsize=(6,4))

		if region==None:
			region=SELF.outer_self._iso

		if SELF.time_format=='monthly':
			running_mean=running_mean_years*len(SELF.outer_self._seasons[season])
			relevenat_time_steps=SELF.get_relevant_time_steps_in_season(SELF.outer_self._seasons[season])

		if SELF.time_format=='10day':
			running_mean=running_mean_years*len(SELF.outer_self._seasons[season])*3
			relevenat_time_steps=SELF.get_relevant_time_steps_in_season(SELF.outer_self._seasons[season])

		if SELF.time_format=='yearly':
			running_mean=running_mean_years
			relevenat_time_steps=range(len(SELF.year))
			if season!='year':
				return(0)

		ax.plot(SELF.time_stamp[relevenat_time_steps],pd.rolling_mean(SELF.area_average[mask_style][region][relevenat_time_steps],running_mean),linestyle='-',label=label,color=color)

		if hasattr(SELF,'model'):
			if SELF.model=='ensemble_mean':
				ensemble,ensemble_mean=SELF.outer_self.find_ensemble([SELF.data_type,SELF.var_name,SELF.scenario])

				relevenat_time_steps=ensemble_mean.get_relevant_time_steps_in_season(SELF.outer_self._seasons[season])
				time_axis=ensemble_mean.time_stamp[relevenat_time_steps]

				ensemble_range=np.zeros([len(ensemble),len(time_axis)])*np.nan

				for member,i in zip(ensemble.values(),range(len(ensemble))):
					relevenat_time_steps=member.get_relevant_time_steps_in_season(SELF.outer_self._seasons[season])
					member_runmean=pd.rolling_mean(member.area_average[mask_style][region][relevenat_time_steps],running_mean)
					for t in member.time_stamp[relevenat_time_steps]:
						ensemble_range[i,np.where(abs(time_axis-t)<1/36.)]=member_runmean[np.where(member.time_stamp[relevenat_time_steps]==t)]
					#ax.plot(member.time_stamp,pd.rolling_mean(member.area_average[mask_style][region],running_mean),linestyle='-',label=label,color='blue',linewidth=0.5)

				ax.fill_between(time_axis,np.percentile(ensemble_range,0,axis=0),np.percentile(ensemble_range,100,axis=0),alpha=0.25,color=color)

		if ylabel==None:ylabel=SELF.var_name.replace('_',' ')
		ax.set_ylabel(ylabel)
		if title==None:title=SELF.name.replace('_',' ')
		ax.set_title(title)

		if y_range!=None:
			ax.set_ylim(y_range)
		
		if show==True:ax.legend(loc='best')
		if out_file==None and show==True:plt.show()
		if out_file!=None:plt.savefig(out_file)

		return(1)

	def plot_annual_cycle(SELF,mask_style='lat_weighted',region=None,period=None,ax=None,out_file=None,title=None,ylabel=None,label='',color='blue'):
		'''
		plot transient of countrywide average
		meta_data: list of strs: meta information required to acces data
		mask_style: str: weighting used to compute countrywide averages
		running_mean: int: years to be averaged in moving average		
		ax: subplot: subplot on which the map will be plotted
		out_file: str: location where the plot is saved
		title: str: title of the plot
		ylabel: str: labe to put on y-axis
		show: logical: show the subplot?
		'''

		if ax!=None:
			show=False

		if ax==None:
			show=True
			fig, ax = plt.subplots(nrows=1, ncols=1,figsize=(6,4))

		if period==None:
			period=[min(SELF.year),max(SELF.year)]

		if region==None:
			region=SELF._iso

		print SELF.steps_in_year,SELF.annual_cycle[mask_style][region][period]

		ax.plot(SELF.steps_in_year,SELF.annual_cycle[mask_style][region][period],linestyle='-',label=label,color=color)

		if hasattr(SELF,'model'):
			if SELF.model=='ensemble_mean':
				ensemble=SELF.outer_self.find_ensemble([SELF.data_type,SELF.var_name,SELF.scenario])[0].values()
				ensemble_annual_cycle=np.vstack([member.annual_cycle[mask_style][region][period] for member in ensemble])

				ax.fill_between(SELF.steps_in_year,np.percentile(ensemble_annual_cycle,0./3.*100,axis=0),np.percentile(ensemble_annual_cycle,3./3.*100,axis=0),alpha=0.25,color=color)


		ax.set_xticks(SELF.steps_in_year) 
		ax.set_xticklabels(['JAN','FEB','MAR','APR','MAI','JUN','JUL','AUG','SEP','OCT','NOV','DEC'])

		if ylabel==None:ylabel=SELF.var_name.replace('_',' ')
		ax.set_ylabel(ylabel)
		if title==None:title=SELF.name.replace('_',' ')
		ax.set_title(title)
		
		if show==True:ax.legend(loc='best')
		if out_file==None and show==True:plt.show()
		if out_file!=None:plt.savefig(out_file)

	def historical_index_validation(SELF,extreme_type='flood',mask_style='lat_weighted',region=None,ax=None,out_file=None,title=None,ylabel=None,label='',color='blue',y_range=None):

		if ax!=None:
			show=False

		if ax==None:
			show=True
			fig, ax = plt.subplots(nrows=1, ncols=1,figsize=(6,4))

		if region==None:
			region=SELF.outer_self._iso

		ax.fill_between(SELF.time_stamp,SELF.time_stamp.copy()*0,SELF.area_average[mask_style][region],linestyle='-',color='black')

		lower,upper=ax.get_ylim()

		for event in SELF.outer_self._extreme_events[extreme_type]:
			if region in event['region'] or event['region']=='n.a.':
				print event
				yr,mn,dy=event['start'].split('-')
				start_time=int(yr)+(30*int(mn)+int(dy))/365.
				yr,mn,dy=event['end'].split('-')
				end_time=int(yr)+(30*int(mn)+int(dy))/365.
				print start_time,end_time
				ax.fill_between([start_time,end_time],[lower,lower],[upper,upper],linestyle='-',color='blue',alpha=0.5)
			
		if show==True:ax.legend(loc='best')
		if out_file==None and show==True:plt.show()
		if out_file!=None:plt.savefig(out_file,dpi=300)








