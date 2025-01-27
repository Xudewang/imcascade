Advanced
=========

A guide of more advanceded and in-depth features and possibilities when runnning ``imcascade``. Currently in progress of being written

If you have additional questions please feel free to reach out to me or raise an issue on github!

Adjusting inital values and bounds
----------------------------------
By default `imcascade` attempts to make  '' smart '' guesses for the initial
values and bounds based on the input variables. These can be easily changed by
using the ``init_dict`` or ``bounds_dict`` arguments when intializing a ``Fitter`` instance
These are both dictionaries, with matching keys, that will be discussed below, where each key should match to a
float for ``init_dict`` and 2 length tuple or list for ``bounds_dict``.

* ``x0`` and ``y0`` - The central location of the object. By default this intial value is the center of the image and the bounds are +/- 10 pixels

* ``phi`` - The position angle in radians, default is :math:`\pi/2` with bounds 0 to :math:`\pi`

* ``q`` - The axis ratio initial value is 0.5 and bounds are 0 to 1

The inital values and boudns for the fluxes of each gaussian components can be
adjusted in several ways. The easist is the specify 're' and 'flux' in ``init_dict``.
This uses a polynomial fit to the exponential relationship derrived in
`Hogg & Lang (2013) <https://ui.adsabs.harvard.edu/abs/2013PASP..125..719H/abstract>`_
to guess the inital values. This lower bounds on the flux of each component is
then :math:`flux/10^5` (or 0 if using linear weight scaling) and the upper bound is the ``flux`` value.

You can also specify using the keys ``a_max`` and ``a_min`` in ``bounds_dict`` to
directly specify the upper and lower bound for the flux of every component. Note that these need to
be specified in logarithmic scale if exploring the fluxes in log scale. These will override the bounds discussed above.

Finally you can specify ``a_i``, where i is the component of interest, in
``init_dict`` and ``bounds_dict`` to make changes to specific components.

Again these will need to be in logarithmic scale if using ``log_weight_scale = True``

If you are using the tilted plane sky model, you can additionally specify those parameters

* ``sky0`` - Overal sky background, estimated as the median of the image

* ``sky1`` - X slope of sky, estimated using the edges of the image

* ``sky2`` - Y slope of sky, estimated using the edges of the image

Fitting options
---------------

``imcascade`` utilized previously written routines for the optimization procedures. For the least squares
minimization we use the `scipy.optimize.least_squares <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html>`_
routine. when using ``run_ls_min()`` the ``ls_kwargs`` input can be used to specify keywords to be passed to the ``least_squares`` function.

Similarly we implemented `dynesty <https://dynesty.readthedocs.io/en/latest/>`_ for Bayesian inference. You can pass arguments through ``run_dynesty()``
for when defining the sampler  using ``sampler_kwargs`` or running the nested sampling using ``run_nested_kwargs()``. Both of these should be dictionaries.


We have found the default options for both these packages work fairly well however performce can likely be increased by tweaking one or more
parameters when using these packages.

Model averaging
---------------

As discussed in our paper, a powerful extension of ``imcascade`` is to run Bayesian inference on a galaxy multiple times with different
using different set of widths. These can then be combined using a Bayesian model averaging approach. For ease of use we have written a
class ``MultiResults`` in the ``results`` module. The input for this class is a list of ``ImcascadeResuts`` instances which are meant meant
to be combined. It contains some (but not all) function contained in ``ImcascadeResuts`` and calculates the joint posterier distribution of
these quantities by weighting each model (i.e. set of widths) by their relative evidence. It is important to make sure you are using results
run on the same images etc. or else it will produce non-sensical results.

Non-circular PSF
----------------

As a extension to the normal mode with a circular PSF, we have implemented the ability to specify a non-circular PSF. To do this use the
parameter ``PSF_shape`` when initializing a ``Fitter`` instance. This should be a dictionary with the keys ``q`` for the axis ratio
and ``phi`` for the position angle. Currently all components of the psf must have the same shape parameters

This increases the time to render a model as no each individual component in the observed profile must be rotated individually
as they will have different position angles. **It has also not been thoroughly tested so use with caution!**


Changing the Likelihood function
--------------------------------
In our implementation of ``imcascade`` we have assumed Gaussian statistics and errors when using the usual :math:`\chi^2` method. However,
In some use cases (or just in general, see `Erwin (2015) <https://arxiv.org/abs/1408.1097>`_ ) it is preferable to assume Poisson statistics and
use the Cash statistic as the likelihood (`Cash (1979) <https://ui.adsabs.harvard.edu/abs/1979ApJ...228..939C/abstract>`_). For the "express" method
the function that gets called to calculate the likelihood is ``log_like_express``, we can simply re-assign the to a function of our choosing, using the
``setattr`` method built in to python. First we have initialized a ``Fitter`` instance under the name ``fitter_cash`` as usual (but with the pixel weights equal to one)
and then we run the following code block

.. code-block:: python

  fitter_cash = initialize_fitter(img, psf, sky_model = False, err = np.ones(img.shape))

  def log_like_cash(self, exp_params):
      "log likelihood using the Cash statistic"

      #Use this function to generate model
      model = self.make_express_model(exp_params)

      #Employing the Cash statistic
      return -1.*np.sum( self.weight *(model - self.img*np.log(model)) )

  setattr(fitter_cash, 'log_like_express', log_like_cash)

In this example we have written our on function to replace the original function. Now when we use ``run_dynesty`` it will call
our new function instead. The function ``self.make_express_model`` generates the model image and the self weight variable contains the
pixel weights (which we have set to 1.) and any mask we have supplied. ``self.img`` contains the input science cutout.

Using this example as a blueprint, it is possible to change the likelihood function to anything your heart desires! It is important
to test whatever function you have used to make sure the answer is what you expect.

Changing the Priors
-------------------
