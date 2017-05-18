import sys,glob,os,pickle
import numpy as np
from netCDF4 import Dataset,netcdftime,num2date
import pandas as pd

sys.path.append('/Users/peterpfleiderer/Documents/Projects/country_analysis/country_analysis_scripts/')
try:del sys.modules['country_analysis'] 
except:pass
from country_analysis import country_analysis
sys.path.append('/Users/peterpfleiderer/Documents/')

os.chdir('/Users/peterpfleiderer/Documents/')

country_iso='BEN'

COU=country_analysis(country_iso,'Projects/country_analysis/'+country_iso+'/')
COU.load_data()

COU.summary()

COU.area_average('lat_weighted',overwrite=True)
# COU.area_average('pop2015_weighted',overwrite=False)
# COU.area_average('pop1990_weighted',overwrite=False)



