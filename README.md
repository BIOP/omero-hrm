# OMERO - HRM

These scripts aim at making the connection between OMERO and HRM more friendly.
Our HRM server works with a shared folder located on another server (HRM-Share folder).
Scripts are uploaded to OMERO.server and can be run from the web interface. 

## Send image to HRM

The first script sends images from OMERO to HRM-Share folder. You can select image(s), dataset(s) or project(s) ids and all images are sent to the shared folder, 
with the same dataset/project hierarchy.

## Retrieve image from HRM

The second script sends back deconvolved images to OMERO. It uploads .ids images to the same project/dataset as raw images, 
adds deconvolution parameters as key-value pairs and attach the .log.txt file as attachment to the image. 
Moreover, it adds ``raw`` and ``hrm`` tags to the raw image, ``deconvolved`` and ``hrm`` tags to the deconvovled
image and transfer all tags from the raw to the deconvolved image.

An option allows you to clean your HRM folder. If you select ``Delete deconvolved images on HRM``, 
only images within the Deconvolved folder of HRM will be deleted.
If you select ``Delete raw images on HRM``, the raw images are also deleted. In both cases, if the 
parent folder is empty, it is automatically deleted as well.
