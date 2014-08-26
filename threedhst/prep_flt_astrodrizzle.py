"""
Align and background-subtract direct and grism FLT images using 
Drizzlepac/Astrodrizzle rather than Multidrizzle

xxx still need full "pair" wrapper to put it all together, including adding direct shifts to grism exposures

"""
import os

try:
    import astropy.io.fits as pyfits
except:
    import pyfits

import numpy as np

import matplotlib.pyplot as plt
import scipy.ndimage as nd

import stsci.convolve

import threedhst

def clean_wcsname(flt='ibhj15wyq_flt.fits', wcsname='TWEAK', ACS=False):
    """
    Workaround for annoying TweakReg feature of not overwriting WCS solns
    """
    im = pyfits.open(flt, mode='update')
    if ACS:
        exts = [1,4]
    else:
        exts = [1]
    
    for ext in exts:
        header = im[ext].header
        for key in header:
            if key.startswith('WCSNAME'):
                if header[key] == wcsname:
                    wcs_ext = key[-1]
                    if key == 'WCSNAME':
                        header[key] = wcsname+'X'
                        #im.flush()
        #
        for key in ['WCSNAME', 'WCSAXES', 'CRPIX1', 'CRPIX2', 'CDELT1', 'CDELT2', 'CUNIT1', 'CUNIT2', 'CTYPE1', 'CTYPE2', 'CRVAL1', 'CRVAL2', 'LONPOLE', 'LATPOLE', 'CRDER1', 'CRDER2', 'CD1_1', 'CD1_2', 'CD2_1', 'CD2_2', 'FITNAME', 'NMATCH', 'RMS_RA', 'RMS_DEC']:
            try:
                header.remove(key+wcs_ext)
            except:
                #print key
                pass
    
    im.flush()
    
def runTweakReg(asn_file='GOODS-S-15-F140W_asn.fits', master_catalog='goodss_radec.dat', final_scale=0.06, ACS=False):
    """
    Wrapper around tweakreg, generating source catalogs separately from 
    `findpars`.
    """
    import glob
    
    import drizzlepac
    from drizzlepac import tweakreg
    from stwcs import updatewcs
    
    import threedhst.prep_flt_astrodrizzle
    
    asn = threedhst.utils.ASNFile(asn_file)
    
    if ACS:
        NCHIP=2
        sci_ext = [1,4]
        wht_ext = [2,5]
        ext = 'flc'
        dext = 'crclean'
    else:
        NCHIP=1
        sci_ext = [1]
        wht_ext = [2]
        ext = 'flt'
        dext = 'flt'
        
    ### Generate CRCLEAN images
    for exp in asn.exposures:
        updatewcs.updatewcs('%s_%s.fits' %(exp, ext))
    
    has_crclean = True
    for exp in asn.exposures:
        has_crclean &= os.path.exists('%s_crclean.fits' %(exp))
    
    if not has_crclean: 
        drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=False, context=False, preserve=False, skysub=True, driz_separate=True, driz_sep_wcs=True, median=True, blot=True, driz_cr=True, driz_cr_corr=True, driz_combine=True)
        
    #### Make SExtractor source catalogs in *each* flt
    for exp in asn.exposures:
        #updatewcs.updatewcs('%s_%s.fits' %(exp, ext))
        for i in range(NCHIP):
            se = threedhst.sex.SExtractor()
            se.options['WEIGHT_IMAGE'] = '%s_%s.fits[%d]' %(exp, dext, wht_ext[i]-1)
            se.options['WEIGHT_TYPE'] = 'MAP_RMS'
            #
            se.params['X_IMAGE'] = True; se.params['Y_IMAGE'] = True
            se.params['MAG_AUTO'] = True
            #
            se.options['CATALOG_NAME'] = '%s_%s_%d.cat' %(exp, ext, sci_ext[i])
            se.options['FILTER'] = 'N'
            se.options['DETECT_THRESH'] = '4'
            se.options['ANALYSIS_THRESH'] = '4'
            #
            se.sextractImage('%s_%s.fits[%d]' %(exp, dext, sci_ext[i]-1))
            threedhst.sex.sexcatRegions('%s_%s_%d.cat' %(exp, ext, sci_ext[i]), '%s_%s_%d.reg' %(exp, ext, sci_ext[i]), format=1)
    
    #### TweakReg catfile
    asn_root = asn_file.split('_asn')[0]
    catfile = '%s.catfile' %(asn_root)
    fp = open(catfile,'w')
    for exp in asn.exposures:
        line = '%s_%s.fits' %(exp, ext)
        for i in range(NCHIP):
            line += ' %s_%s_%d.cat' %(exp, ext, sci_ext[i])
        
        fp.write(line + '\n')
    
    fp.close()
    
    #### First run AstroDrizzle mosaic
    #drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=True, context=False, preserve=False, skysub=True, driz_separate=False, driz_sep_wcs=False, median=False, blot=False, driz_cr=False, driz_combine=True)
    
    #### Make room for TWEAK wcsname
    for exp in asn.exposures:
        threedhst.prep_flt_astrodrizzle.clean_wcsname(flt='%s_%s.fits' %(exp, ext), wcsname='TWEAK', ACS=ACS)
    
    #### Main run of TweakReg
    if ACS:
        refimage = '%s_drc_sci.fits' %(asn_root)
    else:
        refimage = '%s_drz_sci.fits' %(asn_root)
        
    tweakreg.TweakReg(asn_file, refimage=refimage, updatehdr=True, updatewcs=True, catfile=catfile, xcol=2, ycol=3, xyunits='pixels', refcat=master_catalog, refxcol=1, refycol=2, refxyunits='degrees', shiftfile=True, outshifts='%s_shifts.txt' %(asn_root), outwcs='%s_wcs.fits' %(asn_root), searchrad=5, tolerance=12, wcsname='TWEAK', interactive=False, residplot='No plot', see2dplot=False, clean=True, headerlet=True, clobber=True)
    
    #### Run AstroDrizzle again
    if ACS:
        drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=True, final_scale=final_scale, final_pixfrac=0.8, context=False, resetbits=4096, final_bits=576, preserve=False)
    else:
        drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=True, final_scale=final_scale, final_pixfrac=0.8, context=False, resetbits=4096, final_bits=576, preserve=False, driz_cr_snr='5.0 4.0', driz_cr_scale = '2.5 0.7') # , final_wcs=True, final_rot=0)
        
    for exp in asn.exposures:
        files=glob.glob('%s*coo' %(exp))
        files.extend(glob.glob('%s*crclean.fits' %(exp)))
        for file in files:
            os.remove(file)
    
def align_drizzled(images=['MACS2129-35-F814W_drc_sci.fits', 'MACS2129-36-F814W_drc_sci.fits']):
    
    from astropy.table import Table as table
    from drizzlepac import astrodrizzle, tweakreg, tweakback
    
    for image in images:
        root = image.split('_sci.fits')[0]
        se = threedhst.sex.SExtractor()
        se.options['WEIGHT_IMAGE'] = '%s_wht.fits[0]' %(root)
        se.options['WEIGHT_TYPE'] = 'MAP_WEIGHT'
        #
        se.params['X_IMAGE'] = True; se.params['Y_IMAGE'] = True
        se.params['MAG_AUTO'] = True
        #
        se.options['CATALOG_NAME'] = '%s_sci.cat' %(root)
        se.options['FILTER'] = 'N'
        se.options['DETECT_THRESH'] = '5'
        se.options['ANALYSIS_THRESH'] = '5'
        #
        se.sextractImage('%s_sci.fits[0]' %(root))
        threedhst.sex.sexcatRegions('%s_sci.cat' %(root), '%s_sci.reg' %(root), format=1)
        #
        t = table.read('%s_sci.cat' %(root), format='ascii.sextractor')
        np.savetxt('%s_sci.xy' %(root), np.array([t['X_IMAGE'], t['Y_IMAGE']]).T, fmt='%.7f')
        fp = open('%s_sci.catfile' %(root), 'w')
        fp.write('%s_sci.fits %s_sci.xy\n' %(root, root))
        fp.close()
        
    reference = '%s_sci.xy' %(images[0].split('_sci.fits')[0])
    
    for image in images[1:]:
        root = image.split('_sci.fits')[0]
        tweakreg.TweakReg(image, refimage=images[0], updatehdr=True, updatewcs=True, catfile='%s_sci.catfile' %(root), xcol=1, ycol=2, xyunits='pixels', refcat=reference, refxcol=1, refycol=2, refxyunits='pixels', shiftfile=False, searchrad=5, tolerance=12, wcsname='TWEAK3', interactive=False, residplot='No plot', see2dplot=False, clean=True, headerlet=True, clobber=True)
        tweakback.tweakback(image)
    
    pass
    
def subtract_flt_background(root='GOODN-N1-VBA-F105W', scattered_light=False):
    """
    Subtract polynomial background
    """
    import scipy.optimize
    
    import astropy.units as u
    
    from astropy.table import Table as table
    
    import drizzlepac
    import stwcs
    from drizzlepac import astrodrizzle, tweakreg, tweakback
    
    import threedhst
    
    if not os.path.exists('%s_drz_sci.fits' %(root)):
        drizzlepac.astrodrizzle.AstroDrizzle(root+'_asn.fits', clean=False, context=False, preserve=False, skysub=True, driz_separate=True, driz_sep_wcs=True, median=True, blot=True, driz_cr=True, driz_cr_corr=True, driz_combine=True)
    
    se = threedhst.sex.SExtractor()
    se.options['WEIGHT_IMAGE'] = '%s_drz_wht.fits' %(root)
    se.options['WEIGHT_TYPE'] = 'MAP_WEIGHT'
    se.options['CHECKIMAGE_TYPE'] = 'SEGMENTATION'
    se.options['CHECKIMAGE_NAME'] = '%s_drz_seg.fits' %(root)
    #
    se.params['X_IMAGE'] = True; se.params['Y_IMAGE'] = True
    se.params['MAG_AUTO'] = True
    #
    se.options['CATALOG_NAME'] = '%s_drz_sci.cat' %(root)
    se.options['FILTER'] = 'Y'
    se.copyConvFile()
    se.options['FILTER_NAME'] = 'gauss_4.0_7x7.conv'
    se.options['DETECT_THRESH'] = '0.8'
    se.options['ANALYSIS_THRESH'] = '0.8'
    #
    se.sextractImage('%s_drz_sci.fits' %(root))
    #threedhst.sex.sexcatRegions('%s_flt.cat' %(exp), '%s_flt.reg' %(exp), format=1)
    
    #### Blot segmentation map to FLT images for object mask
    asn = threedhst.utils.ASNFile('%s_asn.fits' %(root))
    
    #print 'Read files...'
    ref = pyfits.open('%s_drz_sci.fits' %(root))
    ref_wcs = stwcs.wcsutil.HSTWCS(ref, ext=0)

    seg = pyfits.open('%s_drz_seg.fits' %(root))    
    #### Fill ref[0].data with zeros for seg mask
    #seg_data = ref[0].data
    #seg_data[seg[0].data == 0] = 0
    seg_data = np.cast[np.float32](seg[0].data)
    
    yi, xi = np.indices((1014,1014))
    if scattered_light:
        bg_components = np.ones((4,1014,1014))
        bg_components[1,:,:] = xi/1014.*2
        bg_components[2,:,:] = yi/1014.*2
        bg_components[3,:,:] = pyfits.open(os.getenv('THREEDHST') + '/CONF/G141_scattered_light.fits')[0].data
        NCOMP=4
    else:
        bg_components = np.ones((3,1014,1014))
        bg_components[1,:,:] = xi/1014.*2
        bg_components[2,:,:] = yi/1014.*2
        NCOMP=3
        
    bg_flat = bg_components.reshape((NCOMP,1014**2))
    
    #### Loop through FLTs, blotting reference and segmentation
    for exp in asn.exposures:
        flt = pyfits.open('%s_flt.fits' %(exp)) #, mode='update')
        flt_wcs = stwcs.wcsutil.HSTWCS(flt, ext=1)
        
        ### segmentation        
        print 'Segmentation image: %s_blot.fits' %(exp)
        blotted_seg = astrodrizzle.ablot.do_blot(seg_data, ref_wcs, flt_wcs, 1, coeffs=True, interp='nearest', sinscl=1.0, stepsize=10, wcsmap=None)
        
        mask = (blotted_seg == 0) & (flt['DQ'].data == 0) & (flt[1].data < 5) & (flt[1].data > -1) & (xi > 50) & (yi > 50) & (xi < 964) & (yi < 964)
        data_range = np.percentile(flt[1].data[mask], [2.5, 97.5])
        mask &= (flt[1].data >= data_range[0]) & (flt[1].data <= data_range[1])
        data_range = np.percentile(flt[2].data[mask], [2.5, 97.5])
        mask &= (flt[2].data >= data_range[0]) & (flt[2].data <= data_range[1])
        
        ### Least-sq fit for component normalizations
        data = flt[1].data[mask].flatten()
        wht = (1./flt[2].data[mask].flatten())**2
        templates = bg_flat[:, mask.flatten()]
        p0 = np.zeros(NCOMP)
        p0[0] = np.median(data)
        obj_fun = threedhst.grism_sky.obj_lstsq
        popt = scipy.optimize.leastsq(obj_fun, p0, args=(data, templates, wht), full_output=True, ftol=1.49e-8/1000., xtol=1.49e-8/1000.)
        xcoeff = popt[0]
        model = np.dot(xcoeff, bg_flat).reshape((1014,1014))
        
        # add header keywords of the fit components
        flt = pyfits.open('%s_flt.fits' %(exp), mode='update')
        flt[1].data -= model
        for i in range(NCOMP):
            if 'BGCOMP%d' %(i+1) in flt[0].header:
                flt[0].header['BGCOMP%d' %(i+1)] += xcoeff[i]
            else:
                flt[0].header['BGCOMP%d' %(i+1)] = xcoeff[i]                
        
        flt.flush()
        coeff_str = '  '.join(['%.4f' %c for c in xcoeff])
        threedhst.showMessage('Background subtraction, %s_flt.fits:\n\n  %s' %(exp, coeff_str))

def copy_adriz_headerlets(direct_asn='GOODS-S-15-F140W_asn.fits', grism_asn='GOODS-S-15-G141_asn.fits', force=False, ACS=False):
    """
    Copy Tweaked WCS solution in direct image to the paired grism exposures.
    
    If same number of grism as direct exposures, match the WCS headers
    directly.  If not, just get the overall shift from the first direct 
    exposure and apply that to the grism exposures.
    """
    import stwcs
    from stwcs import updatewcs
    import drizzlepac
    
    direct = threedhst.utils.ASNFile(direct_asn)
    grism = threedhst.utils.ASNFile(grism_asn)
    
    Nd = len(direct.exposures)
    Ng = len(grism.exposures)
    
    if ACS:
        NCHIP=2
        sci_ext = [1,4]
        ext = 'flc'
    else:
        NCHIP=1
        sci_ext = [1]
        ext = 'flt'
        
    if Nd == Ng:
        for i in range(Nd):
            imd = pyfits.open('%s_%s.fits' %(direct.exposures[i], ext))
            #img = pyfits.open('%s_%s.fits' %(grism.exposures[i]))
            #
            for sci in sci_ext:
                #sci_ext=1
                direct_WCS = stwcs.wcsutil.HSTWCS(imd, ext=sci)
                #
                drizzlepac.updatehdr.update_wcs('%s_%s.fits' %(grism.exposures[i], ext), sci, direct_WCS, verbose=True)    
    else:
        #### Get overall shift from a shift-file and apply it to the 
        #### grism exposures
        sf = threedhst.shifts.ShiftFile(direct_asn.replace('_asn.fits', '_shifts.txt'))
        imd = pyfits.open(direct_asn.replace('asn','wcs'))
        print imd.filename()
        direct_WCS = stwcs.wcsutil.HSTWCS(imd, ext='wcs')
        #
        for i in range(Ng):
            img = pyfits.open('%s_%s.fits' %(grism.exposures[i], ext))
            if 'WCSNAME' in img[1].header:
                if img[1].header['WCSNAME'] == 'TWEAK':
                    if force is False:
                        threedhst.showMessage('"TWEAK" WCS already found in %s_flt.fits.\nRun copy_adriz_headerlets with force=True to force update the shifts' %(grism.exposures[i]), warn=True)
                        continue
            #
            updatewcs.updatewcs('%s_%s.fits' %(grism.exposures[i], ext))
            drizzlepac.updatehdr.updatewcs_with_shift('%s_%s.fits' %(grism.exposures[i], ext), direct_WCS, rot=sf.rotate[0], scale=sf.scale[0], xsh=sf.xshift[0], ysh=sf.yshift[0], wcsname='TWEAK')
  
def subtract_acs_grism_background(asn_file='RXJ2248-08-G800L_asn.fits', final_scale=None):

    import glob
    import os
    
    import drizzlepac
    from drizzlepac import tweakreg
    from stwcs import updatewcs
    
    import threedhst.prep_flt_astrodrizzle
    
    ### First pass to flag CRs and make crclean images
    drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=False, context=False, preserve=False, skysub=True, driz_separate=True, driz_sep_wcs=True, median=True, blot=True, driz_cr=True, driz_cr_corr=True, driz_combine=True)
    
    ### add mdrizsky back to values, fit on crclean but subtract from flc
    asn = threedhst.utils.ASNFile(asn_file)
    
    sky1 = pyfits.open(os.getenv('THREEDHST') + '/CONF/ACS.WFC.CHIP1.msky.1.fits')
    sky2 = pyfits.open(os.getenv('THREEDHST') + '/CONF/ACS.WFC.CHIP2.msky.1.fits')    
    skies = [sky1, sky2]
    extensions = [1,4] ### SCI extensions
    
    for exp in asn.exposures:
        flt = pyfits.open(exp+'_flc.fits', mode='update')
        #crc = pyfits.open(exp+'_crclean.fits')
        ### Loop through ACS chips
        for j in [0,1]:
            ext = extensions[j]
            #
            exptime = flt[0].header['EXPTIME']
            mask = flt['dq', j+1].data == 0
            ratio = flt['sci', j+1].data/exptime/skies[j][0].data
            med = np.median(ratio[mask])
            #
            mask2 = mask & ((flt['sci',j+1].data-med*exptime)/flt['err',j+1].data < 3)
            med2 = np.median(ratio[mask2])
            #
            flt['sci', j+1].data -= med2*exptime*skies[j][0].data     
            flt['sci', j+1].header['MDRIZSKY'] = 0. #.update('MDRIZSKY', med2*exptime)
            print '%s chip%d: %.3f' %(exp, j+1, med2)
        #
        ### Write updates
        flt.flush()
    
    drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=True, skysub=False, skyuser='MDRIZSKY', final_scale=final_scale, final_pixfrac=0.8, context=False, resetbits=4096, final_bits=576, preserve=False) # , final_wcs=True, final_rot=0)
    
def subtract_grism_background(asn_file='GDN1-G102_asn.fits', PATH_TO_RAW='../RAW/', final_scale=0.06, visit_sky=True, column_average=True, mask_grow=18):
    """
    Subtract master grism sky from FLTs
    """
    import os
    import scipy.ndimage as nd
    import pyregion
    
    from drizzlepac import astrodrizzle
    import drizzlepac
    
    from stwcs import updatewcs
    import stwcs
    
    import threedhst.grism_sky as bg
    
    asn = threedhst.utils.ASNFile(asn_file)
    root = asn_file.split('_asn')[0]
    
    ### Rough background subtraction
    threedhst.process_grism.fresh_flt_files(asn_file, from_path=PATH_TO_RAW, preserve_dq=False)
    flt = pyfits.open('%s_flt.fits' %(asn.exposures[0]))
    GRISM = flt[0].header['FILTER']
    
    bg.set_grism_flat(grism=GRISM, verbose=True)
    
    sky_images = {'G141':['zodi_G141_clean.fits', 'excess_lo_G141_clean.fits', 'G141_scattered_light.fits'],
                  'G102':['zodi_G102_clean.fits', 'excess_G102_clean.fits']}
    
    zodi = pyfits.open(os.getenv('THREEDHST')+'/CONF/%s' %(sky_images[GRISM][0]))[0].data
    
    for exp in asn.exposures:
        updatewcs.updatewcs('%s_flt.fits' %(exp))
        flt = pyfits.open('%s_flt.fits' %(exp), mode='update')
        #flt = pyfits.open('%s_flt.fits' %(exp))
        flt[1].data *= bg.flat
        #
        mask = (flt['DQ'].data == 0)
        data_range = np.percentile(flt[1].data[mask], [20, 80])
        mask &= (flt[1].data >= data_range[0]) & (flt[1].data <= data_range[1]) & (flt[2].data != 0) & np.isfinite(flt[1].data) & np.isfinite(flt[2].data)
        ### Least-sq fit for component normalizations
        data = flt[1].data[mask].flatten()
        wht = (1./flt[2].data[mask].flatten())**2
        zodi_mask = zodi[mask].flatten()
        coeff_zodi = np.sum(data*zodi_mask*wht)/np.sum(zodi_mask**2*wht)
        flt[1].data -= zodi*coeff_zodi
        flt.flush()
        threedhst.showMessage('Rough background for %s (zodi): %0.4f' %(exp, coeff_zodi))
        #templates = bg_flat[:, mask.flatten()]
        
    ### Run astrodrizzle to make DRZ mosaic, grism-SExtractor mask
    drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=True, context=False, preserve=False, skysub=True, driz_separate=True, driz_sep_wcs=True, median=True, blot=True, driz_cr=True, driz_combine=True, final_wcs=False)
    
    se = threedhst.sex.SExtractor()
    se.options['WEIGHT_IMAGE'] = '%s_drz_wht.fits' %(root)
    se.options['WEIGHT_TYPE'] = 'MAP_WEIGHT'
    se.options['CHECKIMAGE_TYPE'] = 'SEGMENTATION'
    se.options['CHECKIMAGE_NAME'] = '%s_drz_seg.fits' %(root)
    #
    se.params['X_IMAGE'] = True; se.params['Y_IMAGE'] = True
    se.params['MAG_AUTO'] = True
    #
    se.options['CATALOG_NAME'] = '%s_drz_sci.cat' %(root)
    se.options['FILTER'] = 'Y'
    se.copyConvFile(grism=True)
    se.options['FILTER_NAME'] = 'grism.conv'
    se.options['DETECT_THRESH'] = '0.7'
    se.options['ANALYSIS_THRESH'] = '0.7'
    #
    se.sextractImage('%s_drz_sci.fits' %(root))
    
    #### Blot segmentation map to FLT images for object mask
    ref = pyfits.open('%s_drz_sci.fits' %(root))
    ref_wcs = stwcs.wcsutil.HSTWCS(ref, ext=0)

    seg = pyfits.open('%s_drz_seg.fits' %(root))
    seg_data = np.cast[np.float32](seg[0].data)
            
    #### Loop through FLTs, blotting reference and segmentation
    threedhst.showMessage('%s: Blotting grism segmentation masks.' %(root))
    
    for exp in asn.exposures:
        flt = pyfits.open('%s_flt.fits' %(exp))
        flt_wcs = stwcs.wcsutil.HSTWCS(flt, ext=1)
        ### segmentation
        #print 'Segmentation image: %s_blot.fits' %(exp)
        blotted_seg = astrodrizzle.ablot.do_blot(seg_data, ref_wcs, flt_wcs, 1, coeffs=True, interp='nearest', sinscl=1.0, stepsize=10, wcsmap=None)
        seg_grow = nd.maximum_filter((blotted_seg > 0)*1, size=8)
        pyfits.writeto('%s_flt.seg.fits' %(exp), header=flt[1].header, data=seg_grow, clobber=True)
        
    ### Run background subtraction scripts
    threedhst.process_grism.fresh_flt_files(asn_file, from_path=PATH_TO_RAW, preserve_dq=False)
    for exp in asn.exposures:
        updatewcs.updatewcs('%s_flt.fits' %(exp))
        #threedhst.grism_sky.remove_grism_sky(flt=exp+'_flt.fits', list=sky_images[GRISM], path_to_sky=os.getenv('THREEDHST')+'/CONF/', verbose=True, second_pass=True, overall=True)
    
    if visit_sky:
        threedhst.grism_sky.remove_visit_sky(asn_file=asn_file, list=sky_images[GRISM], add_constant=False, column_average=column_average, mask_grow=mask_grow)
    else:
        for exp in asn.exposures:
            threedhst.grism_sky.remove_grism_sky(flt='%s_flt.fits' %(exp), list=sky_images[GRISM],  path_to_sky = os.getenv('THREEDHST')+'/CONF/', out_path='./', verbose=False, plot=False, flat_correct=True, sky_subtract=True, second_pass=column_average, overall=True, combine_skies=False, sky_components=True, add_constant=False)
            
    ### Astrodrizzle again to reflag CRs and make cleaned mosaic
    drizzlepac.astrodrizzle.AstroDrizzle(asn_file, clean=True, skysub=False, skyuser='MDRIZSKY', final_scale=final_scale, final_pixfrac=0.8, context=False, resetbits=4096, final_bits=576, preserve=False, driz_cr_snr='5.0 4.0', driz_cr_scale = '2.5 0.7') # , final_wcs=True, final_rot=0)

def get_vizier_cat(image='RXJ2248-IR_sci.fits', ext=0, catalog="II/246"):
    """
    Get a list of RA/Dec coords from a Vizier catalog that can be used
    for WCS alignment.
    
    `catalog` is any catalog ID recognized by Vizier, e.g.: 
        "II/328/allwise": WISE
        "II/246": 2MASS
    
    """
    import threedhst.dq
    import astropy.wcs as pywcs
    from astropy.table import Table as table
    import astropy.io.fits as pyfits
    
    import astroquery
    from astroquery.vizier import Vizier
    import astropy.coordinates as coord
    import astropy.units as u
    
    im = pyfits.open(image)
    
    wcs = pywcs.WCS(im[ext].header)
    #wcs = pywcs.WCS(pyfits.getheader('Q0821+3107-F140W_drz.fits', 1))

    Vizier.ROW_LIMIT = -1
            
    r0, d0 = wcs.wcs_pix2world([[im[ext].header['NAXIS1']/2., im[ext].header['NAXIS2']/2.]], 1)[0]
    foot = wcs.calc_footprint()
    
    corner_radius = np.sqrt((foot[:,0]-r0)**2/np.cos(d0/360.*2*np.pi)**2 + (foot[:,1]-d0)**2).max()*60*1.1

    try:
        c = coord.ICRS(ra=r0, dec=d0, unit=(u.deg, u.deg))
    except:
        c = coord.ICRSCoordinates(ra=r0, dec=d0, unit=(u.deg, u.deg))
        
    #### something with astropy.coordinates
    # c.icrs.ra.degree = c.icrs.ra.degrees
    # c.icrs.dec.degree = c.icrs.dec.degrees
    #
    vt = Vizier.query_region(c, radius=u.Quantity(corner_radius, u.arcminute), catalog=[catalog])
    if not vt:
        threedhst.showMessage('No matches found in Vizier %s @ (%.6f, %.6f).\n\nhttp://vizier.u-strasbg.fr/viz-bin/VizieR?-c=%.6f+%.6f&-c.rs=8' %(catalog, r0, d0, r0, d0), warn=True)
        return False
    
    vt = vt[0]
            
    #### Make a region file
    ra_list, dec_list = vt['RAJ2000'], vt['DEJ2000']
    print 'Vizier, found %d objects in %s.' %(len(ra_list), catalog)
    
    fp = open('%s.vizier.radec' %(image.split('.fits')[0]), 'w')
    fpr = open('%s.vizier.reg' %(image.split('.fits')[0]), 'w')
    
    fp.write('# %s, r=%.1f\'\n' %(catalog, corner_radius))
    fpr.write('# %s, r=%.1f\'\nfk5\n' %(catalog, corner_radius))
    for ra, dec in zip(ra_list, dec_list):
        fp.write('%.7f %.7f\n' %(ra, dec))
        fpr.write('circle(%.6f, %.6f, 0.5")\n' %(ra, dec))
    
    fpr.close()
    fp.close()
    
    return True
    
    
def prep_direct_grism_pair(direct_asn='goodss-34-F140W_asn.fits', grism_asn='goodss-34-G141_asn.fits', radec=None, raw_path='../RAW/', mask_grow=18, scattered_light=False, final_scale=None, skip_direct=False, ACS=False, jump=False):
    """
    Process both the direct and grism observations of a given visit
    """
    import threedhst.prep_flt_astrodrizzle as prep
    import drizzlepac
    from stwcs import updatewcs
    
    import time
    
    t0 = time.time()
    
    #direct_asn='goodss-34-F140W_asn.fits'; grism_asn='goodss-34-G141_asn.fits'; radec=None; raw_path='../RAW/'
    #radec = os.getenv('THREEDHST') + '/ASTRODRIZZLE_FLT/Catalog/goodss_radec.dat'
    
    ################################
    #### Direct image processing
    ################################
    
    #### xx add astroquery 2MASS/SDSS workaround for radec=None
    
    if not skip_direct:

        #### Get fresh FLTS from ../RAW/
        asn = threedhst.utils.ASNFile(direct_asn)
        if ACS:
            for exp in asn.exposures:
                print 'cp %s/%s_flc.fits.gz .' %(raw_path, exp)
                os.system('cp %s/%s_flc.fits.gz .' %(raw_path, exp))
                os.system('gunzip %s_flc.fits.gz' %(exp))
        else:
            threedhst.process_grism.fresh_flt_files(direct_asn, from_path=raw_path)
        
        if (not ACS):
            #### Subtract WFC3/IR direct backgrounds
            prep.subtract_flt_background(root=direct_asn.split('_asn')[0], scattered_light=scattered_light)
            #### Flag IR CRs again within runTweakReg
        
        #### Run TweakReg
        if (radec is None) & (not ACS):
            drizzlepac.astrodrizzle.AstroDrizzle(direct_asn, clean=True, final_scale=None, final_pixfrac=0.8, context=False, final_bits=576, preserve=False, driz_cr_snr='5.0 4.0', driz_cr_scale = '2.5 0.7') # ,
        else:
            prep.runTweakReg(asn_file=direct_asn, master_catalog=radec, final_scale=None, ACS=ACS)
    
        #### Subtract background of direct ACS images
        if ACS:
            for exp in asn.exposures:
                flc = pyfits.open('%s_flc.fits' %(exp), mode='update')
                for ext in [1,4]:
                    threedhst.showMessage('Subtract background from %s_flc.fits[%d] : %.4f' %(exp, ext, flc[ext].header['MDRIZSKY']))
                    flc[ext].data -= flc[ext].header['MDRIZSKY']
                    flc[ext].header['MDRIZSK0'] = flc[ext].header['MDRIZSKY']
                    flc[ext].header['MDRIZSKY'] = 0.
                #
                flc.flush()
        else:
            pass
            #### Do this later, gives segfaults here???
            #prep.subtract_flt_background(root=direct_asn.split('_asn')[0], scattered_light=scattered_light)
            #### Flag CRs again on BG-subtracted image
            #drizzlepac.astrodrizzle.AstroDrizzle(direct_asn, clean=True, final_scale=None, final_pixfrac=0.8, context=False, final_bits=576, preserve=False, driz_cr_snr='5.0 4.0', driz_cr_scale = '2.5 0.7') # ,
        
    ################################
    #### Grism image processing
    ################################
    
    if grism_asn:
        if ACS:
            asn = threedhst.utils.ASNFile(grism_asn)
            for exp in asn.exposures:
                print 'cp %s/%s_flc.fits.gz .' %(raw_path, exp)
                os.system('cp %s/%s_flc.fits.gz .' %(raw_path, exp))
                os.system('gunzip %s_flc.fits.gz' %(exp))
                updatewcs.updatewcs('%s_flc.fits' %(exp))

            prep.copy_adriz_headerlets(direct_asn=direct_asn, grism_asn=grism_asn, ACS=True)
            prep.subtract_acs_grism_background(asn_file=grism_asn, final_scale=None)
        else:
            #### Remove the sky and flag CRs
            prep.subtract_grism_background(asn_file=grism_asn, PATH_TO_RAW='../RAW/', final_scale=None, visit_sky=True, column_average=True, mask_grow=mask_grow)

            #### Copy headers from direct images
            if radec is not None:
                prep.copy_adriz_headerlets(direct_asn=direct_asn, grism_asn=grism_asn, ACS=False)
                #### Run CR rejection with final shifts
                drizzlepac.astrodrizzle.AstroDrizzle(grism_asn, clean=True, skysub=False, final_scale=None, final_pixfrac=0.8, context=False, final_bits=576, preserve=False, driz_cr_snr='5.0 4.0', driz_cr_scale = '2.5 0.7')
        
    if not grism_asn:
        t1 = time.time()
        threedhst.showMessage('direct: %s\n\nDone (%d s).' %(direct_asn, int(t1-t0)))
    else:
        t1 = time.time()
        threedhst.showMessage('direct: %s\ngrism: %s\n\nDone (%d s).' %(direct_asn, grism_asn, int(t1-t0)))
    