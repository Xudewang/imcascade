import numpy as np
import matplotlib.pyplot as plt
import asdf
from scipy.optimize import root_scalar

from imcascade.fitter import fitter_from_ASDF,Fitter
from imcascade.utils import get_med_errors,vars_to_use


def calc_flux_input(weights,sig, cutoff = None):
    if cutoff == None:
        return np.sum(weights, axis = -1)
    else:
        return np.sum(weights*(1. - np.exp(-1*cutoff**2/ (2*sig**2)) ), axis = -1 )

def r_root_func(r,f_L, weights,sig,cutoff):
    return f_L - np.sum(weights*(1. - np.exp(-1.*r**2 / (2*sig**2)) ),axis = -1 ) / calc_flux_input(weights,sig,cutoff = cutoff)


class ImcascadeResults():
    """A class used for collating imcascade results and performing analysis

        Parameters
        ----------
        Obj: imcascade.fitter.Fitter class, dictionary or str
            Object which contains the data to be analyzed. Can be a Fitter object
            once the run_(ls_min,dynesty, emcee) has been ran. If it is a dictionay
            needs to contain, at bare minmum the variables sig, Ndof, Ndof_sky,
            Ndof_gauss, log_weight_scale and either min_param or posterior.
            If a string is passed it will be interreted as a file locations with
            an ASDF file containing the neccesary information.

        thin_posterior: int (optional)
            Factor by which to thin the posterior distribution by. While one wants
            to ensure the posterior is large enough, some of this analysis can
            take time if you have >10^6 samples so this is one way to speed up
            this task but use with caution.
"""
    def __init__(self, Obj, thin_posterior = 1):
        """Initialize a Task instance
"""
        if type(Obj) == Fitter:
            self.obj_type = 'class'
            dict_obj = vars(Obj)
        if type(Obj) == dict:
            self.obj_type = 'dict'
            dict_obj = Obj
        if type(Obj) == str:
            self.obj_type = 'file'
            file = asdf.open(Obj)
            dict_obj = file.tree

        self.input = Obj

        #To-do write better function to do this that can handle missing values
        for var_name in vars_to_use:
            if var_name in dict_obj.keys():
                    setattr(self, var_name, dict_obj[var_name] )
        if 'posterier'in dict_obj.keys():
            setattr(self, 'posterior', dict_obj['posterier'] )

        if hasattr(self, 'posterior'):
            self.x0 = self.posterior[::int(thin_posterior),0]
            self.y0 = self.posterior[::int(thin_posterior),1]
            self.q = self.posterior[::int(thin_posterior),2]
            self.pa = self.posterior[::int(thin_posterior),3]
            self.weights = self.posterior[::int(thin_posterior),4:4+self.Ndof_gauss]

            if self.sky_model: self.sky_params = self.posterior[::int(thin_posterior),4+self.Ndof_gauss:]

        elif hasattr(self, 'min_param'):
            self.x0 = self.min_param[0]
            self.y0 = self.min_param[1]
            self.q = self.min_param[2]
            self.pa = self.min_param[3]
            self.weights = self.min_param[4:4+self.Ndof_gauss]
            if self.sky_model: self.sky_params = self.min_param[4+self.Ndof_gauss:]

        #Account for if weights are in log_scale
        if self.log_weight_scale:
            self.weights = 10**self.weights

    def calc_flux(self, cutoff = None):
        """Calculate flux of given results

        Parameters
        ----------
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width use

        Returns
        -------
        Flux: float or Array
            Total flux of best fit model
"""
        if cutoff == None:
            flux_cur = np.sum(self.weights, axis = -1)
        else:
            flux_cur = np.sum(self.weights*(1 - np.exp(-1*cutoff**2/ (2*self.sig**2) ) ), axis = -1 )
        self.flux = flux_cur
        return flux_cur

    def _min_calc_rX(self,X,cutoff = None):
        """Old and slow Function to calculate the radius containing X percent of the light

        Parameters
        ----------
        X: float
            Fractional radius of intrest to calculate. if X < 1 will take as a fraction,
            else will interpret as percent and divide X by 100. i.e. to calculate
            the radius containing 20% of the light, once can either pass X = 20 or 0.2
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width used

        Returns
        -------
        r_X: float or Array
            The radius containg X percent of the light
"""
        if X> 1:
            frac_use = X/100.
        else:
            frac_use = X
        f_cur = lambda w: root_scalar(r_root_func, bracket = [0,5*np.max(self.sig)], args = (frac_use,w,self.sig,cutoff) ).root

        if self.weights.ndim == 1:
            return f_cur(self.weights)
        if self.weights.ndim == 2:
            return np.array(list(map(f_cur, self.weights)) )

    def calc_rX(self,X,cutoff = None):
        """Function to calculate the radius containing X percent of the light

        Parameters
        ----------
        X: float
            Fractional radius of intrest to calculate. if X < 1 will take as a fraction,
            else will interpret as percent and divide X by 100. i.e. to calculate
            the radius containing 20% of the light, once can either pass X = 20 or 0.2
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width used

        Returns
        -------
        r_X: float or Array
            The radius containg X percent of the light
"""
        if X> 1:
            frac_use = X/100.
        else:
            frac_use = X

        #Calculate CoG
        r = np.linspace(0,np.max(self.sig)*1.5, num = 150)
        cog = self.calc_cog(r)

        #locate Area near target
        fl_target = self.calc_flux(cutoff = cutoff)*frac_use
        arg_min = np.argmin(np.abs(cog - fl_target), axis = 0 )


        #Use 2nd degree polynomical interpolation to calculate target radius
        # When compared more accurate but slower root finding, accurate ~1e-4 %, more then good enough
        if self.weights.ndim == 1:
            if arg_min == 149: arg_min -= 1

            fl_0 = cog[arg_min -1]
            fl_1 = cog[arg_min]
            fl_2 = cog[arg_min + 1]

        if self.weights.ndim == 2:
            arg_min[arg_min == 149] = 148
            fl_0 = cog[arg_min -1,np.arange(cog.shape[1])]
            fl_1 = cog[arg_min,np.arange(cog.shape[1])]
            fl_2 = cog[arg_min + 1,np.arange(cog.shape[1])]


        r_0 = r[arg_min - 1]
        r_1 =  r[arg_min]
        r_2 = r[arg_min + 1 ]

        r_target = (fl_target - fl_1)*(fl_target - fl_2)/(fl_0 - fl_1)/(fl_0 - fl_2)*r_0
        r_target += (fl_target - fl_0)*(fl_target - fl_2)/(fl_1 - fl_0)/(fl_1 - fl_2)*r_1
        r_target += (fl_target - fl_0)*(fl_target - fl_1)/(fl_2 - fl_0)/(fl_2 - fl_1)*r_2

        return r_target


    def calc_r90(self,cutoff = None):
        """Wrapper function to calculate the radius containing 90% of the light

        Parameters
        ----------
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width use

        Returns
        -------
        r_90: float or Array
            The radius containg 90 percent of the light
"""
        r90_cur = self.calc_rX(90., cutoff = cutoff)
        self.r90 = r90_cur
        return r90_cur

    def calc_r80(self,cutoff = None):
        """Wrapper function to calculate the radius containing 80% of the light

        Parameters
        ----------
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width use

        Returns
        -------
        r_80: float or Array
            The radius containg 80 percent of the light
"""
        r80_cur = self.calc_rX(80., cutoff = cutoff)
        self.r80 = r80_cur
        return r80_cur

    def calc_r50(self,cutoff = None):
        """Wrapper function to calculate the radius containing 50% of the light,
        or the effective radius

        Parameters
        ----------
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width use

        Returns
        -------
        r_50: float or Array
            The radius containg 50 percent of the light
"""
        r50_cur = self.calc_rX(50., cutoff = cutoff)
        self.r50 = r50_cur
        return r50_cur

    def calc_r20(self,cutoff = None):
        """Wrapper function to calculate the radius containing 20% of the light

        Parameters
        ----------
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width use

        Returns
        -------
        r_20: float or Array
            The radius containg 20 percent of the light
"""
        r20_cur = self.calc_rX(20., cutoff = cutoff)
        self.r20 = r20_cur
        return r20_cur

    def calc_sbp(self,r, return_ind = False):
        """Function to calculate surface brightness profiles for the given results

        Parameters
        ----------
        r: float or array
            Radii (in pixels) at which to evaluate the surface brightness profile
        return_ind: bool (optional)
            If False will only return the sum of all gaussian, i.e. the best fit profile.
            If true will return an array with +1 dimensions containing the profiles
            of each individual gaussian component

        Returns
        -------
        SBP: array
            Surface brightness profiles evaluated at 'r'. If 'return_ind = True',
            returns the profile of each individual gaussian component
"""

        #r needs to be an array to work with np.newaxis below
        if type(r) == float:
            r = np.array([r,])

        if np.isscalar(self.q):
            q_use = np.array([ self.q, ])
        else:
            q_use = np.copy(self.q)

        prof_all = self.weights/(2*np.pi*q_use[:,np.newaxis]*self.sig**2) * np.exp(-r[:,np.newaxis,np.newaxis]**2/ (2*self.sig**2))
        prof_all = prof_all.squeeze()

        if return_ind:
            return prof_all
        else:
            return np.sum(prof_all, axis = -1)

    def calc_obs_sbp(self, r, return_ind = False):
        """Function to calculate the observed surface brightness profiles, i.e. convolved with the PSF for the given results

        Parameters
        ----------
        r: float or array
            Radii (in pixels) at which to evaluate the surface brightness profile

        return_ind: bool (optional)
            If False will only return the sum of all gaussian, i.e. the best fit profile.
            If true will return an array with +1 dimensions containing the profiles
            of each individual gaussian component

        Returns
        -------
        obsereved SBP: array
            Observed surface brightness profiles evaluated at 'r'. If 'return_ind = True',
            returns the profile of each individual gaussian component
"""
        if not self.has_psf:
            print ('Need PSF to calculate observed SBP')
            return 0
        #r needs to be an array to work with np.newaxis below
        if type(r) == float:
            r = np.array([r,])

        if np.isscalar(self.q):
            q_use = np.array([ self.q, ])
        else:
            q_use = np.copy(self.q)

        final_var = (self.sig**2 + self.psf_sig[:,None]**2).ravel()

        final_q = np.sqrt( (self.sig[:,None]**2 * q_use*q_use+ self.psf_sig[:,None,None]**2) )
        final_q = np.moveaxis(final_q, -1,0)
        final_q = np.moveaxis(final_q, 2,1)
        final_q = final_q.reshape(self.weights.shape[0], self.weights.shape[1]*len(self.psf_a), order = 'F') / np.sqrt(final_var)


        final_a = self.weights*self.psf_a[:,np.newaxis,np.newaxis]
        final_a = np.moveaxis(final_a,0,-1)

        final_a = final_a.reshape(self.weights.shape[0], self.weights.shape[1]*len(self.psf_a), order = 'F')

        prof_all = final_a/(2*np.pi*final_q*final_var) * np.exp(-r[:,np.newaxis,np.newaxis]**2/ (2*final_var))
        prof_all = prof_all.squeeze()

        if return_ind:
            return prof_all
        else:
            return np.sum(prof_all, axis = -1)

    def calc_cog(self, r, return_ind = False, norm = False, cutoff = None):
        """Function to calculate curves-of-growth for the given results

        Parameters
        ----------
        r: float or array
            Radii (in pixels) at which to evaluate the surface brightness profile
        return_ind: bool (optional)
            If False will only return the sum of all gaussian, i.e. the best fit profile.
            If true will return an array with +1 dimensions containing the profiles
            of each individual gaussian component
        norm: Bool (optional)
            Wether to normalize curves-of-growth to total flux, calculated using
            'self.calc_flux'. Does nothing if 'return_ind = True'
        cutoff: Float (optional)
            Cutoff radius used in 'self.calc_flux', only is used if 'norm' is True

        Returns
        -------
        COG: array
            curves-of-growth evaluated at 'r'. If 'return_ind = True',
            returns the profile of each individual gaussian component
"""
        #r needs to be an array to work with np.newaxis below
        if type(r) == float:
            r = np.array([r,])

        cog_all = self.weights*( 1. - np.exp(-r[:,np.newaxis,np.newaxis]**2/ (2*self.sig**2)) )
        cog_all = cog_all.squeeze()

        if return_ind:
            return cog_all
        else:
            if norm:
                return np.sum(cog_all, axis = -1)/ self.calc_flux(cutoff = cutoff)
            else:
                return np.sum(cog_all, axis = -1)

    def calc_obs_cog(self, r, return_ind = False, norm = False, cutoff = None):
        """Function to calculate the observed curve of growth, i.e. convolved with the PSF for the given results

        Parameters
        ----------
        r: float or array
            Radii (in pixels) at which to evaluate the surface brightness profile
        return_ind: bool (optional)
            If False will only return the sum of all gaussian, i.e. the best fit profile.
            If true will return an array with +1 dimensions containing the profiles
            of each individual gaussian component
        norm: Bool (optional)
            Wether to normalize curves-of-growth to total flux, calculated using
            'self.calc_flux'. Does nothing if 'return_ind = True'
        cutoff: Float (optional)
            Cutoff radius used in 'self.calc_flux', only is used if 'norm' is True

        Returns
        -------
        observed COG: array
            curves-of-growth evaluated at 'r'. If 'return_ind = True',
            returns the profile of each individual gaussian component
"""
        if not self.has_psf:
            print ('Need PSF to calculate observed cog')
            return 0
        #r needs to be an array to work with np.newaxis below
        if type(r) == float:
            r = np.array([r,])

        if np.isscalar(self.q):
            q_use = np.array([ self.q, ])
        else:
            q_use = np.copy(self.q)

        final_var = (self.sig**2 + self.psf_sig[:,None]**2).ravel()

        final_q = np.sqrt( (self.sig[:,None]**2 * q_use*q_use+ self.psf_sig[:,None,None]**2) )
        final_q = np.moveaxis(final_q, -1,0)
        final_q = np.moveaxis(final_q, 2,1)
        final_q = final_q.reshape(self.weights.shape[0], self.weights.shape[1]*len(self.psf_a), order = 'F') / np.sqrt(final_var)


        final_a = self.weights*self.psf_a[:,np.newaxis,np.newaxis]
        final_a = np.moveaxis(final_a,0,-1)

        final_a = final_a.reshape(self.weights.shape[0], self.weights.shape[1]*len(self.psf_a), order = 'F')

        cog_all = final_a*(1 - np.exp(-r[:,np.newaxis,np.newaxis]**2/ (2*final_var) ) )
        cog_all = cog_all.squeeze()

        if return_ind:
            return cog_all
        else:
            if norm:
                return np.sum(cog_all, axis = -1)/ self.calc_flux(cutoff = cutoff)
            else:
                return np.sum(cog_all, axis = -1)

    def run_basic_analysis(self, zpt = None, cutoff = None, errp_lo = 16, errp_hi =84,\
      save_results = False, save_file = './imcascade_results.asdf'):
        """Function to calculate a set of common variables and save the save the results

        Parameters
        ----------
        zpt: float (optional)
            photometric zeropoint for the data. if not 'None', will also calculate
            magnitude
        cutoff: float (optional)
            Radius out to which to consider the profile. Generally this should be
            around the half-width of the image or the largest gaussian width use
        errp_(lo,hi): float (optional)
            percentiles to be used to calculate the lower and upper error bars from
            the posterior distribution. Default is 16 and 84, corresponding to 1-sigma
            for a guassian distribtuion
        save_results: bool (optional)
            If true will save results to file. If input is a file, will add
            to given file, else will save to file denoted by 'save_file' (see below)
        save_file: str
            String to describe where to save file, only applicaple if the input
            is not a file.

        Returns
        -------
        res_dict:  dictionary
            Dictionary contining the results of the analysis
"""

        #Run all basic calculations neccesary
        self.calc_flux(cutoff = cutoff)
        self.calc_r20(cutoff = cutoff)
        self.calc_r50(cutoff = cutoff)
        self.calc_r80(cutoff = cutoff)
        self.calc_r90(cutoff = cutoff)

        res_dict = {}
        if self.weights.ndim == 1:
            res_dict['flux'] = self.flux
            if zpt != None: res_dict['mag'] = -2.5*np.log10(self.flux) + zpt

            #Save All Radii
            res_dict['r20'] = self.r20
            res_dict['r50'] = self.r50
            res_dict['r80'] = self.r80
            res_dict['r90'] = self.r90

            #Save concentration indexes
            res_dict['C80_20'] = self.r80 / self.r20
            res_dict['C90_50'] = self.r90 / self.r50
        else:
            res_dict['flux'] = get_med_errors(self.flux,lo = errp_lo, hi = errp_hi)
            if zpt != None:
                res_dict['mag'] = get_med_errors(-2.5*np.log10(self.flux) + zpt,lo = errp_lo, hi = errp_hi)

            res_dict['r20'] = get_med_errors(self.r20,lo = errp_lo, hi = errp_hi)
            res_dict['r50'] = get_med_errors(self.r50,lo = errp_lo, hi = errp_hi)
            res_dict['r80'] = get_med_errors(self.r80,lo = errp_lo, hi = errp_hi)
            res_dict['r90'] = get_med_errors(self.r90,lo = errp_lo, hi = errp_hi)

            res_dict['C80_20'] = get_med_errors(self.r80 / self.r20,lo = errp_lo, hi = errp_hi)
            res_dict['C90_50'] = get_med_errors(self.r90 / self.r50,lo = errp_lo, hi = errp_hi)

        if save_results:
            if self.obj_type == 'file':
                input_asdf = asdf.open(self.input)
                input_asdf.tree.update(res_dict)
                input_asdf.write_to(save_file)
            else:
                dict_to_save = vars(self).copy()
                dict_to_save.pop('input')
                dict_to_save.pop('obj_type')

                if hasattr(self, 'posterior'):
                    for key in ['flux','r20','r50','r80','r90']:
                        dict_to_save[key+'_post'] = dict_to_save.pop(key)

                dict_to_save.update(res_dict)
                file = asdf.AsdfFile(dict_to_save)
                file.write_to(save_file)

        return res_dict

    def calc_iso_r(self,I, zpt = None, pix_scale = None):
        """Function to calculate the isophotal radius

        Parameters
        ----------
        I: float
            Surface brightness target to define the isophotal radii. By defualt this shoud be in
            image units unless both zpt and pix_scale are given, then I is interpreted as
            mag per arcsec^2.
        zpt: float (optional)
            zeropoint magnitude of image, used to convert I to mag per arcsec^2
        pix_scale: float (optional)
            pixel scale in units of arcseconds/pixel, used to convert I to mag per arcsec^2

        Returns
        -------
        r_I: float or Array
            The radius, in pixel units, where the surface brightness profile matches I
"""
        #Calculate sbp
        r = np.linspace(0,np.max(self.sig)*1.5, num = 150)
        sbp = self.calc_sbp(r)

        if zpt is None and  pix_scale is None:
            I_target = I
        elif zpt is None or pix_scale is None:
            print ('Need zpt and pix_scale to calculate mag per arcsec^2')
            return 0
        else:
            I_target = 10**( (I - zpt)/-2.5)*pix_scale**2

        #locate Area near target
        arg_min = np.argmin(np.abs(sbp - I_target), axis = 0 )


        #Use 2nd degree polynomical interpolation to calculate target radius
        # When compared more accurate but slower root finding, accurate ~1e-4 %, more then good enough
        if self.weights.ndim == 1:
            if arg_min == 149: arg_min -= 1
            if arg_min ==0: arg_min += 1

            I_0 = sbp[arg_min -1]
            I_1 = sbp[arg_min]
            I_2 = sbp[arg_min + 1]

        if self.weights.ndim == 2:
            arg_min[arg_min == 149] = 148
            arg_min[arg_min == 0] = 1

            I_0 = sbp[arg_min -1,np.arange(sbp.shape[1])]
            I_1 = sbp[arg_min,np.arange(sbp.shape[1])]
            I_2 = sbp[arg_min + 1,np.arange(sbp.shape[1])]


        r_0 = r[arg_min - 1]
        r_1 =  r[arg_min]
        r_2 = r[arg_min + 1 ]

        r_target = (I_target - I_1)*(I_target - I_2)/(I_0 - I_1)/(I_0 - I_2)*r_0
        r_target += (I_target - I_0)*(I_target - I_2)/(I_1 - I_0)/(I_1 - I_2)*r_1
        r_target += (I_target - I_0)*(I_target - I_1)/(I_2 - I_0)/(I_2 - I_1)*r_2

        return r_target

    def calc_petro_r(self_cls, P_ratio = 0.2, r_fac_min = 0.8, r_fac_max = 1.25):
        """Function to calculate the petrosian radii of a galaxy

        Parameters
        ----------
        P_ratio: float (optional)
            The Petrosian ratio which defines the Petrosian radii, default is 0.2
        r_fac_min: float (optional)
            lower multiplicative factor which is used to integrate flux, default 0.8
        r_fac_max: float (optional)
            higher multiplicative factor which is used to inegrate flux, default 1.25

        Returns
        -------
        r_I: float or Array
            The radius, in pixel units, where the surface brightness profile matches I
"""
        #Calculate sbp
        r = np.linspace(0.1,np.max(self_cls.sig)*1.5, num = 150)

        cog_lo = self_cls.calc_cog(r*r_fac_min)
        cog_md = self_cls.calc_cog(r)
        cog_hi = self_cls.calc_cog(r*r_fac_max)

        ratio = (cog_hi - cog_lo)/cog_md / (r_fac_max**2 - r_fac_min**2)

        #locate Area near target
        arg_min = np.argmin(np.abs(ratio - P_ratio), axis = 0 )


        #Use 2nd degree polynomical interpolation to calculate target radius
        if self_cls.weights.ndim == 1:
            if arg_min == 149: arg_min -= 1
            if arg_min ==0: arg_min += 1

            I_0 = ratio[arg_min -1]
            I_1 = ratio[arg_min]
            I_2 = ratio[arg_min + 1]

        if self_cls.weights.ndim == 2:
            arg_min[arg_min == 149] = 148
            arg_min[arg_min == 0] = 1

            I_0 = ratio[arg_min -1,np.arange(ratio.shape[1])]
            I_1 = ratio[arg_min,np.arange(ratio.shape[1])]
            I_2 = ratio[arg_min + 1,np.arange(ratio.shape[1])]


        r_0 = r[arg_min - 1]
        r_1 =  r[arg_min]
        r_2 = r[arg_min + 1 ]

        r_target = (P_ratio - I_1)*(P_ratio - I_2)/(I_0 - I_1)/(I_0 - I_2)*r_0
        r_target += (P_ratio - I_0)*(P_ratio - I_2)/(I_1 - I_0)/(I_1 - I_2)*r_1
        r_target += (P_ratio - I_0)*(P_ratio - I_1)/(I_2 - I_0)/(I_2 - I_1)*r_2

        return r_target
    
    def make_diagnostic_fig(self):
        """Function which generates a diagnostic figure to assess fit

        Parameters
        ----------

        Returns
        -------
        fig:  matplotlib figure
            matplotlib figure object
"""
        if self.obj_type == 'dict':
            print ('Cannot make diagnostic figure with dict as an input, please use a fitter class or an asdf file')
        elif self.obj_type == 'class':
            fitter = self.input 
        elif self.obj_type == 'file':
            fitter = fitter_from_ASDF(self.input)
        
        fig,((ax1,ax2,ax3,ax4),(ax5,ax6,ax7,ax8) ) = plt.subplots(2,4, figsize = (13,6.5))

        param_no_sky = np.copy(self.min_param)
        if fitter.sky_model:
            param_no_sky[-3:] = 0
            best_fit_sky = fitter.get_sky_model(self.min_param[-3:])
        else:
            best_fit_sky = np.zeros(shape= fitter.img.shape)
        img = np.ma.masked_array(fitter.img, mask = fitter.mask)
        best_fit_mod = fitter.make_model(param_no_sky)

        resid = img - best_fit_mod - best_fit_sky

        vlo,vhi = np.percentile(np.arcsinh(img.flatten()), [30,99]) 

        ax1.set_title('Image')
        ax1.imshow(np.arcsinh(img), vmin = vlo,vmax = vhi, cmap = 'cividis')
        ax1.axis('off')

        ax2.set_title('Best Fit Obs. Galaxy Model')
        ax2.imshow(np.arcsinh(best_fit_mod), vmin = vlo,vmax = vhi, cmap = 'cividis')
        ax2.axis('off')

        ax3.set_title('Best Fit Sky Model')
        ax3.imshow(np.arcsinh(best_fit_sky), vmin = vlo,vmax = vhi, cmap = 'cividis')
        ax3.axis('off')

        resid_std = np.std(resid)
        ax4.set_title('Residuals')
        ax4.imshow(np.arcsinh(resid),cmap = 'twilight', vmin = np.arcsinh(-3.5*resid_std), vmax = np.arcsinh(3.5*resid_std))
        ax4.axis('off')

        rplot = np.linspace(0, fitter.sig[-1]*1.2, num = 50)
        sbp_ind = self.calc_sbp(rplot, return_ind = True)
        sbp_tot = sbp_ind.sum(axis = -1)
        cog = self.calc_cog(rplot)
        rms_med = np.median(1./np.sqrt(fitter.weight) )
        abs_sky_med = np.median(np.abs(best_fit_sky))

        if len(sbp_tot.shape) > 1:
            sbp_tot = sbp_tot.mean(axis = 1)
            cog = cog.mean(axis = 1)
            sbp_ind = sbp_ind.mean(axis = 1)

        ax5.plot(rplot,sbp_tot, 'k-', lw = 2)
        ax5.plot(rplot,sbp_ind, 'r--')
        ax5.plot([rplot[0],rplot[-1]], [rms_med,rms_med], 'C0:', lw = 3, label = 'Med. RMS/pix')
        ax5.plot([rplot[0],rplot[-1]], [abs_sky_med,abs_sky_med], 'C1:', lw = 3, label = 'Med. |Sky Model|')

        ax5.set_yscale('log')
        ax5.set_ylim(sbp_tot[-1] *0.4,sbp_tot[0]*1.4)
        ax5.set_xlabel('radius (pixels)')
        ax5.set_title('Intr. SBP')
        ax5.legend(frameon = False)

        ax6.plot(rplot, cog,'k-', lw = 2)
        #ax6.set_yscale('log')
        ax6.set_xlabel('radius (pixels)')
        ax6.set_title('Intr. Curve-of-growth')

        ax7.axis ('off')
        ax8.axis('off')

        ax7_str = f'Flux = {self.calc_flux():.2f} \nr_eff = {self.calc_r50():.2f} pixels\nq = {self.q:.2f}\nPA ={self.pa:.2f} rad'
        ax7.text(0.01,0.99,ax7_str, transform = ax7.transAxes, fontsize = 16, ha = 'left', va= 'top')

        ax8_str = f'# of components = {fitter.Ndof_gauss:d}\nPSF? - {fitter.has_psf}\nSky? - {fitter.sky_model}'
        ax8.text(0.01,0.99,ax8_str, transform = ax8.transAxes, fontsize = 16, ha = 'left', va= 'top')
        fig.subplots_adjust(wspace = 0.2)
        
        return fig

class MultiResults():
    ''' A Class to analyze and combine multiple ImcascadeResults classes using evidence weighting'''
    def __init__(self, lofr):
        self.lofr = lofr
        self.num_res = len(lofr)
        self.len_post = np.array([res.posterior.shape[0] for res in self.lofr])
        self.lnz_list = np.array([res.logz for res in self.lofr])
        self.lnz_err_list = np.array([res.logz_err for res in self.lofr])
        #Calculate weights accounting for differnce in evidence and difference in length of posterior
        self.rel_weight = np.exp(self.lnz_list - np.max(self.lnz_list) )* ( np.min(self.len_post)/ self.len_post )

        self.rng = rng = np.random.default_rng()

    def calc_cog(self,r,num = 1000):
        all_cog = np.hstack([res.calc_cog(r) for res in self.lofr])
        weights_cur = np.hstack([[self.rel_weight[i]]*self.len_post[i] for i in range(self.num_res)] )

        #Normalize to 1
        weights_cur /= np.sum(weights_cur)
        cog_samp = self.rng.choice(all_cog, p=weights_cur, axis=1,size = int(num) )
        return cog_samp

    def calc_obs_cog(self,r,num = 1000):
        all_cog = np.hstack([res.calc_obs_cog(r) for res in self.lofr])
        weights_cur = np.hstack([[self.rel_weight[i]]*self.len_post[i] for i in range(self.num_res)] )

        #Normalize to 1
        weights_cur /= np.sum(weights_cur)
        cog_samp = self.rng.choice(all_cog, p=weights_cur, axis=1,size = int(num) )
        return cog_samp

    def calc_sbp(self,r,num = 1000):
        all_sbp = np.hstack([res.calc_sbp(r) for res in self.lofr])
        weights_cur = np.hstack([[self.rel_weight[i]]*self.len_post[i] for i in range(self.num_res)] )

        #Normalize to 1
        weights_cur /= np.sum(weights_cur)
        sbp_samp = self.rng.choice(all_sbp, p=weights_cur, axis=1,size = int(num) )
        return sbp_samp

    def calc_obs_sbp(self,r,num = 1000):
        all_sbp = np.hstack([res.calc_obs_sbp(r) for res in self.lofr])
        weights_cur = np.hstack([[self.rel_weight[i]]*self.len_post[i] for i in range(self.num_res)] )

        #Normalize to 1
        weights_cur /= np.sum(weights_cur)
        sbp_samp = self.rng.choice(all_sbp, p=weights_cur, axis=1,size = int(num) )

        return sbp_samp

    def calc_flux(self,cutoff = None, num = 1000):
        all_flux = np.hstack([res.calc_flux(cutoff = cutoff) for res in self.lofr])
        weights_cur = np.hstack([[self.rel_weight[i]]*self.len_post[i] for i in range(self.num_res)] )

        #Normalize to 1
        weights_cur /= np.sum(weights_cur)
        flux_samp = self.rng.choice(all_flux, p=weights_cur, size = int(num) )
        return flux_samp

    def calc_rX(self,X,cutoff = None, num = 1000):

        all_rX = np.hstack([res.calc_rX(X,cutoff = cutoff) for res in self.lofr])
        weights_cur = np.hstack([[self.rel_weight[i]]*self.len_post[i] for i in range(self.num_res)] )

        #Normalize to 1
        weights_cur /= np.sum(weights_cur)
        rX_samp = self.rng.choice(all_rX, p=weights_cur, size = int(num) )
        return rX_samp
