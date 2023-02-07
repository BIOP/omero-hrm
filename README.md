# OMERO - HRM

These scripts aim at making the connection between OMERO and HRM more friendly.
Our HRM server works with a shared folder located on an other server (HRM-Share folder).
Scripts are uploaded to OMERO.server and can be run from the web interface. 

## Send image to HRM

The first script sends images from OMERO to HRM-Share folder. You can select image(s), dataset(s) or project(s) ids and all images are sent to the shared folder, 
with the same dataset/project hierarchy.

## Retrieve image from HRM

The second script sends back deconvolved images to OMERO. It uploads .ids images to the same project/dataset as raw images, 
adds deconvolution parameters as key-value pairs and attach the .log.txt file as attachment to the image. 

