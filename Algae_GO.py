#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 21 08:38:44 2018

@author: Joseph Cook, joe.cook@sheffield.ac.uk

This file calculates the optical properties (single scattering albedo, assymetry parameter,
mass absorption coefficient and extinction, scattering and absorption cross sections) for
algal cells shaped as arbitrarily large cylinders. The optical properties
are then saved into netCDF files in the correct format for loading into one of
the models in the BioSNICAR radiative transfer model family.

The main function calc_optical_params() is based upon the equations of Diedenhoven et al (2014)
who provided a python script as supplementary material for their paper:

"A flexible parameterization for shortwave optical properties of ice crystals" by 
Bastiaan van Diedenhoven; Andrew S. Ackerman; Brian Cairns; Ann M. Fridlind
accepted for publication in J. Atmos. Sci. (2013)

The original code can be downloaded from:
https://www.researchgate.net/publication/259821840_ice_OP_parameterization

The optical properties are calculated using a parameterization of geometric optics
calculations (Macke et al., JAS, 1996).

The script is divided into three functions. The first is a preprocessing function
that ensures the wavelengths and real/imaginary parts of the refractive index for ice is
provided in the correct waveband and correct spectral resolution to interface with the
BioSNICAR_GO model. The imaginary refractive indices are taken from a separate script that
mixes algal pigments and calculates a bulk refractive index for the cell. The real
refractive index is assumed to be 1.4 here (after Dauchet et al., 2015)

There are no user defined inouts for the preprocessing function, it can simply be
run as 

reals, imags, wavelengths = preprocess()

The calc_optical_params() function takes several inputs. reals, imags and wavelengths
are output by preprocess() and cell radius and length are user defined.
The code then calculates volume, aspect ratio, area etc inside the 
function. The optical parameters are returned.

Optional plots and printed values for the optical params are provided by setting
plots to true and the dimensions of the crystals can be reported by setting
report_dims to true in the function call.

The final function, net_cdf_updater() is used to dump the optical parameters and
metadata into a netcdf file and save it into the working directory to be used as
a lookup library for the two-stream radiative transfer model BioSNICAR_GO.

The function calls are provided at the bottom of this script in a loop, where the
user can define the range of side lengths and depths to be looped over.

NOTE: The extinction coefficient in the current implementation is 2 for all size parameters 
as assumed in the conventional geometric optics approximation.

"""

import numpy as np
import sys
import matplotlib.pyplot as plt
from scipy import interpolate
from shutil import copyfile
from netCDF4 import Dataset
import pandas as pd
import xarray as xr

filepath = '/home/joe/Code/BioSNICAR_GO/Algal_Optical_Props/'


def preprocess_RI():
    
    wavelengths = np.arange(0.305,5,0.01)
    
    reals = pd.read_csv('/home/joe/Desktop/Machine_Learn_Tutorial/Algae_GO/temp_real.csv',header=None)
    reals = reals[0:4695]
    reals = reals[0:-1:10]
    reals=np.array(reals)
    
    imags = pd.read_csv('/home/joe/Desktop/CW_BioSNICAR_Experiment/CW_bio_5_KK.csv',header=None)
    imags=np.array(imags)
    
    MAC = pd.read_csv('/home/joe/Desktop/CW_BioSNICAR_Experiment/CW_bio_5_MAC.csv',names = ['vals'], header=None, index_col=None)
    MAC = np.array(MAC['vals'])
    
    return reals, imags, MAC, wavelengths



def calc_optical_params(r,depth,reals,imags,wavelengths,plots=False,report_dims = False):
    
    SSA_list = []
    Assy_list = []
    absXS_list = []
    MAC_list = []
    Chi_abs_list = []
    X_list = []
    density = 1400
    diameter = 2*r
    V = depth*(np.pi*r**2)    # volume of cylinder
    Reff = (V/((4/3)*np.pi))**1/3  # effective radius (i.e. radius of sphere with equal volume to real cylinder)
    Area_total = 2*(np.pi*r**2)+(2*np.pi*r)*(depth)  #total surface area - 2 x ends plus circumference * length 
    #Area = np.mean((np.pi*r**2,diameter*depth))   # projected area
    Area = Area_total/4           
    ar = diameter/depth
    delta = 0.3
    
    for i in np.arange(0,len(wavelengths),1):
      
        mr = reals[i]
        mi = imags[i]
        wl = wavelengths[i]
        
        #------------------------------------------------
        #---------- input tables (see Figs. 4 and 7) ----
        #------------------------------------------------
        # SSA parameterization
        a = [  0.457593 ,  20.9738 ] #for ar=1
        
        # SSA correction for AR != 1 (Table 2)
        nc1 = 3
        nc2 = 4
        c_ij = np.zeros(nc1*nc2*2).reshape((nc1,nc2,2))
        #   ---------- Plates ----------  
        c_ij[:,0,0] = [  0.000527060 ,  0.309748   , -2.58028  ]
        c_ij[:,1,0] = [  0.00867596  , -0.650188   , -1.34949  ]
        c_ij[:,2,0] = [  0.0382627   , -0.198214   , -0.674495 ]
        c_ij[:,3,0] = [  0.0108558   , -0.0356019  , -0.141318 ]
        #   --------- Columns ----------
        c_ij[:,0,1] = [  0.000125752 ,  0.387729   , -2.38400  ]
        c_ij[:,1,1] = [  0.00797282  ,  0.456133   ,  1.29446  ]
        c_ij[:,2,1] = [  0.00122800  , -0.137621   , -1.05868  ]
        c_ij[:,3,1] = [  0.000212673 ,  0.0364655  ,  0.339646 ]
        
        # diffraction g parameterization
        b_gdiffr = [ -0.822315 , -1.20125    ,  0.996653 ]
        
        # raytracing g parameterization ar=1
        p_a_eq_1 = [  0.780550 ,  0.00510997 , -0.0878268 ,  0.111549 , -0.282453 ]
        
        #---- g correction for AR != 1 (Also applied to AR=1 as plate) (Table 3)
        nq1 = 3
        nq2 = 7 
        q_ij = np.zeros(nq1*nq2*2).reshape((nq1,nq2,2))
        #   ---------- Plates ----------  
        q_ij[:,0,0] = [ -0.00133106  , -0.000782076 ,  0.00205422 ]
        q_ij[:,1,0] = [  0.0408343   , -0.00162734  ,  0.0240927  ]
        q_ij[:,2,0] = [  0.525289    ,  0.418336    , -0.818352   ]
        q_ij[:,3,0] = [  0.443151    ,  1.53726     , -2.40399    ]
        q_ij[:,4,0] = [  0.00852515  ,  1.88625     , -2.64651    ]
        q_ij[:,5,0] = [ -0.123100    ,  0.983854    , -1.29188    ]
        q_ij[:,6,0] = [ -0.0376917   ,  0.187708    , -0.235359   ]
        #   ---------- Columns ----------
        q_ij[:,0,1] = [ -0.00189096  ,  0.000637430 ,  0.00157383 ]
        q_ij[:,1,1] = [  0.00981029  ,  0.0409220   ,  0.00908004 ]
        q_ij[:,2,1] = [  0.732647    ,  0.0539796   , -0.665773   ]
        q_ij[:,3,1] = [ -1.59927     , -0.500870    ,  1.86375    ]
        q_ij[:,4,1] = [  1.54047     ,  0.692547    , -2.05390    ]
        q_ij[:,5,1] = [ -0.707187    , -0.374173    ,  1.01287    ]
        q_ij[:,6,1] = [  0.125276    ,  0.0721572   , -0.186466   ]
        
        #--------- refractive index correction of asymmetry parameter
        c_g = np.zeros(4).reshape(2,2)
        c_g[:,0] = [  0.96025050 ,  0.42918060 ]
        c_g[:,1] = [  0.94179149 , -0.21600979 ]
        #---- correction for absorption 
        s = [  1.00014  ,  0.666094 , -0.535922 , -11.7454 ,  72.3600 , -109.940 ]
        u = [ -0.213038 ,  0.204016 ]
        
        # -------- selector for plates or columns
        if ar > 1.:
            col_pla = 1 #columns
        else:
            col_pla = 0 #plates & compacts
            
        #------------------------------------------------
        #------------ Size parameters -------------------
        #------------------------------------------------
        
        #--- absorption size parameter (Fig. 4, box 1)
        Chi_abs = mi/wl*V/Area
        #----- scattering size parameter (Fig. 7, box 1)
        Chi_scat = 2.*np.pi*np.sqrt(Area/np.pi)/wl
        
        #------------------------------------------------
        #------------ SINGLE SCATTERING ALBEDO ----------
        #------------------------------------------------
        
        if Chi_abs > 0:
            w_1= 1.- a[0] * (1.-np.exp(-Chi_abs*a[1]))  #for AR=1 (Fig. 4, box 2)
            l=np.zeros(nc1)
            for i in range(nc2): l[:] += c_ij[:,i,col_pla] * np.log10(ar)**i  #(Fig. 4, box 3)
            D_w= l[0]*np.exp( -(np.log( Chi_abs )- l[2] )**2 / (2.*l[1]**2))/( Chi_abs *l[1]*np.sqrt(2.*np.pi)) #(Fig. 4, box 3)
            w = w_1 + D_w #(Fig. 4, box 4)
        else:
            w = 1.
        
        #------------------------------------------------
        #--------------- ASYMMETRY PARAMETER ------------
        #------------------------------------------------
        
        # diffraction g
        g_diffr = b_gdiffr[0] * np.exp(b_gdiffr[1]*np.log(Chi_scat)) + b_gdiffr[2] #(Fig. 7, box 2)
        g_diffr = max([g_diffr,0.5])
        
        # raytracing g at 862 nm
        g_1 = 0.
        for i in range(len(p_a_eq_1)): g_1 += p_a_eq_1[i]*delta**i #(Fig. 7, box 3)
        
        p_delta=np.zeros(nq1) 
        for i in range(nq2): p_delta += q_ij[:,i,col_pla]*np.log10(ar)**i #(Fig. 7, box 4)
        Dg = 0.
        for i in range(nq1): Dg += p_delta[i]*delta**i #(Fig. 7, box 4)
        g_rt = 2.*(g_1 + Dg)-1.  #(Fig. 7, box 5)
        
        #--------- refractive index correction of asymmetry parameter (Fig. 7, box 6)
        epsilon = c_g[0,col_pla]+c_g[1,col_pla]*np.log10(ar)
        mr1 = 1.3038 #reference value @ 862 nm band
        C_m = abs((mr1-epsilon)/(mr1+epsilon)*(mr+epsilon)/(mr-epsilon)) #abs function added according to corrigendum to the original paper
        
        #---- correction for absorption (Fig. 7, box 7)
        if Chi_abs > 0:
            C_w0 = 0.
            for i in range(len(s)): C_w0 += s[i]*(1.-w)**i
            k = np.log10(ar)*u[col_pla]
            C_w1 = k*w-k+1.    
            C_w = C_w0*C_w1
        else: C_w = 1.
        
        # raytracing g at required wavelength
        g_rt_corr = g_rt*C_m*C_w #(Fig. 7, box 9)
        
        #------ Calculate total asymmetry parameter and check g_tot <= 1 (Fig. 7, box 9)
        g_tot = 1./(2.*w)*( (2.*w-1.)*g_rt_corr + g_diffr )
        g_tot = min([g_tot,1.])
        
        absXS = ((1-(np.exp(-4*np.pi*mi*V/Area*wavelengths[i])))*Area) 
        X = (2*np.pi*Reff)/wl
        
        X_list.append(X)
        Chi_abs_list.append(Chi_abs)
        SSA_list.append(w)
        Assy_list.append(g_tot)
        absXS_list.append(absXS)
    
    if plots:
        plt.figure(1)    
        plt.plot(wavelengths,SSA_list,label='{}x{}'.format(r,depth)),plt.ylabel('SSA'),plt.xlabel('Wavelength (um)'),plt.grid(False),plt.legend(loc='best',ncol=2)
        plt.figure(2)
        plt.plot(wavelengths,Assy_list,label='{}x{}'.format(r,depth)),plt.ylabel('Assymetry Parameter'),plt.xlabel('Wavelength (um)'),plt.grid(False),plt.legend(loc='best',ncol=2)
        plt.figure(3)
        plt.plot(wavelengths,absXS_list,label='{}x{}'.format(r,depth)),plt.ylabel('Absorption Cross Section'),plt.xlabel('Wavelength (um)'),plt.grid(False),plt.legend(loc='best',ncol=2)
        plt.figure(4)
        plt.plot(wavelengths,X_list,label='{}x{}'.format(r,depth)),plt.ylabel('Size Parameter X'),plt.xlabel('Wavelength (um)'),plt.grid(False),plt.legend(loc='best',ncol=2)
        plt.figure(5)
        plt.plot(wavelengths,MAC,label='{}x{}'.format(r,depth)),plt.ylabel('MAC'),plt.xlabel('Wavelength (um)'),plt.grid(False),plt.legend(loc='best',ncol=2)
        
    if report_dims:
        print('cell diameter = ',np.round(diameter,2),' (micron)')
        print('cell length = ',depth,' (micron)')
        print('aspect ratio = ',ar)
        print('cell volume = ', np.round(V,2),' (micron^3)')
        print('Effective radius = ', np.round(Reff,2),' (micron)')
        print("projected area = ", np.round(Area,2))
        print() # line break
        
    return Assy_list,SSA_list,absXS_list,MAC,depth,r,Chi_abs_list,Reff,X_list


def net_cdf_updater(filepath,Assy_list,SSA_list,absXS_list,MAC,depth,r,density):

    with xr.open_dataset(filepath+'algae_geom_template.nc') as algfile:
        algfile.drop(['ext_xsc','sca_xsc','abs_xsc','sca_cff_mss','abs_cff_mss','bnd_nbr'])
        algfile.variables['asm_prm'][:] = np.squeeze(Assy_list)
        algfile.variables['ss_alb'][:] = np.squeeze(SSA_list)
        algfile.variables['abs_xsc'][:] = np.squeeze(absXS_list)
        algfile.variables['ext_cff_mss'][:] = MAC
        algfile.variables['depth'][:] =depth
        algfile.assign({'r':r})
        algfile.variables['prt_dns'][:] = density   
        algfile.attrs['medium_type'] = 'air'
        algfile.attrs['description'] = 'Optical properties for algal cell: cylinder of radius {}um and length {}um'.format(str(r),str(depth)) 
        algfile.attrs['psd'] = 'monodisperse'
        algfile.to_netcdf(str(filepath+'algae_geom_{}_{}.nc'.format(str(r),str(depth))))
    
    return

###############################################################################
##########################  FUNCTON CALLS ####################################

#reals,imags,MAC, wavelengths = preprocess_RI()
#Assy_list,SSA_list,absXS_list,MAC_list,depth,r,Chi_abs_list,Reff,X_list = calc_optical_params(4,40,reals,imags,wavelengths,plots=True,report_dims = True)
#net_cdf_updater(filepath,Assy_list,SSA_list,absXS_list,MAC,depth,r,density=1400)


for r in np.arange(1,11,1):
    for depth in np.arange(1,40,1):
            reals, imags, MAC, wavelengths = preprocess_RI()
            Assy_list,SSA_list,absXS_list,MAC_list,depth,r,Chi_abs_list,Reff,X_list = calc_optical_params(r,depth,reals,imags,wavelengths,plots=True,report_dims = True)
            net_cdf_updater(filepath,Assy_list,SSA_list,absXS_list,MAC_list,depth,r,density=1500)