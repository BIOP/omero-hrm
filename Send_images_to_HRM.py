"""
 MIF/Send_images_to_HRM.py
 Send all images in the specified containers (project, dataset, images) and save them in HRM-Share user folder
-----------------------------------------------------------------------------
  Copyright (C) 2023
  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
  You should have received a copy of the GNU General Public License along
  with this program; if not, write to the Free Software Foundation, Inc.,
  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
------------------------------------------------------------------------------
Created by Rémy Dornier
"""
import omero
from omero.gateway import BlitzGateway
import omero.scripts as scripts
import os
import sys
from omero.rtypes import rstring
from omero.plugins.download import DownloadControl


DATA_TYPE_PARAM_NAME = "Data_Type"
OVERWRITE_PARAM_NAME = "Overwrite_images_on_HRM"
ID_PARAM_NAME = "IDs"
downloaded_fileset = []


class StdOutHandle():
    """
    File handle for writing bytes to std.out
    """
    # https://github.com/pexpect/pexpect/pull/31/files
    @staticmethod
    def write(b):
        # Handle stdout.write for bytes
        return sys.stdout.write(b.decode('ascii', 'replace'))


def download_image(conn, target_obj, path, download_existing_images):
    """
    Download an image to the given path
    return downloading status

    Method partially taken from https://github.com/imcf/hrm-omero
    and https://gist.github.com/will-moore/a9f90c97b5b6f1a0da277a5179d62c5a
    """
    # Download the files composing the image
    fset = target_obj.getFileset()
    fset_id = fset.getId()

    if not fset:
        print("ERROR", f"ERROR: no original file(s) for [%s] found!" % target_obj.getId())
        return False

    if fset_id in downloaded_fileset:
        print("WARNING", f"Image part of the same fileset %s! Skipping..." % fset_id)
        return True

    # mimic the Java gateway download by adding a fileset folder
    path = os.path.join(path, "Fileset_%s" % fset.getId())

    if download_existing_images and os.path.exists(path) and len(os.listdir(path)) > 0:
        delete_previous_fileset(path)

    dc = DownloadControl()
    downloaded = False
    try:
        dc.download_fileset(conn, fset, path)
        downloaded = True
        print("SUCCESS", f"downloading fileset %s to '%s' done !" % (fset_id, path))
    except omero.ValidationException or omero.ResourceError as err:
        print("ERROR", f"ERROR: downloading fileset %s to '%s' failed: \n %s" % (fset_id, path, err.message))
    except Exception as err:
        print("ERROR", f"ERROR: downloading fileset %s to '%s' failed: \n %s" % (fset_id, path, err))

    downloaded_fileset.append(fset.getId())
    return downloaded


def delete_previous_fileset(fileset_path):
    """Delete image in the raw folder
    ----------
    fileset_path : str
        Path to image to delete.
    """
    for path in os.listdir(fileset_path):
        # check if current path is a file
        file = os.path.join(fileset_path, path)
        if os.path.isfile(file):
            print("INFO", f"Delete file [%s]" % file)
            os.remove(file)
        else:
            delete_previous_fileset(file)
            print("INFO", f"Delete folder [%s]" % file)
            os.rmdir(file)


def build_path(root, project_name, dataset_name):
    """
    Build an omero-like and HRM compatible path (Raw/omero/project/dataset)
    return the path
    """
    if os.path.exists(root) and os.path.isdir(root):
        raw_folder = os.path.join(root, "Raw")
        if not os.path.isdir(raw_folder):
            os.makedirs(raw_folder)

        omero_folder = os.path.join(raw_folder, "omero")
        if not os.path.isdir(omero_folder):
            os.makedirs(omero_folder)

        project_folder = os.path.join(omero_folder, project_name)
        if not os.path.isdir(project_folder):
            os.makedirs(project_folder)

        dataset_folder = os.path.join(project_folder, dataset_name)
        if not os.path.isdir(dataset_folder):
            os.makedirs(dataset_folder)

        return dataset_folder
    else:
        return None


def process_image(conn, image, root, download_existing_images):
    """
    Download the image
    return 1 if owner has been added, 0 otherwise
    """

    dataset = image.getParent()
    if dataset is None:
        dataset_name = "None"
        project_name = "None"
    else:
        dataset_name = "{}_{}".format(dataset.getId(), dataset.getName())
        project = dataset.getParent()
        if project is None:
            project_name = "None"
        else:
            project_name = "{}_{}".format(project.getId(), project.getName())

    path = build_path(root, project_name, dataset_name)

    if path is None:
        return 0

    return 1 if download_image(conn, image, path, download_existing_images) else 0


def process_dataset(conn, dataset, project_name, root, download_existing_images):
    """
    Download all images within the given dataset
    return the number of processed images
    """
    n_image = 0
    dataset_name = "{}_{}".format(dataset.getId(), dataset.getName())
    path = build_path(root, project_name, dataset_name)

    if path is None:
        return 0

    for image in dataset.listChildren():
        n_image += (1 if download_image(conn, image, path, download_existing_images) else 0)

    return n_image, (1 if n_image == dataset.countChildren() else 0)


def process_project(conn, project, root, download_existing_images):
    """
    Download all images within the given project
    return the number of processed images & datasets
    """
    n_dataset = 0
    n_image = 0
    project_name = "{}_{}".format(project.getId(), project.getName())
    for dataset in project.listChildren():
        n_image_tmp, n_dataset_tmp = process_dataset(conn, dataset, project_name, root, download_existing_images)
        n_dataset += n_dataset_tmp
        n_image += n_image_tmp

    return n_image, n_dataset, (1 if n_dataset == project.countChildren() else 0)


def download_images_for_hrm(conn, script_params):
    """
    Get the given container(s) or given experimenter(s) and scan all their children to add
    data owner as a key-value pair to all of them.
    """

    # select the object type (image, dataset, project, well, plate, screen, user)
    object_type = script_params[DATA_TYPE_PARAM_NAME]
    # enter its corresponding ID (except for 'user' : enter the username)
    object_id_list = script_params[ID_PARAM_NAME]
    # root HRM path
    root = "/mnt"#/hrmshare"  # script_params["HRM_path"]
    # boolean to overwrite
    download_existing_images = script_params[OVERWRITE_PARAM_NAME]

    n_image = 0
    n_dataset = 0
    n_project = 0
    user_name = ""

    # check if the root directory exists ==> necessary because sv-nas1 server is mounted on OMERO server
    if os.path.isdir(root):
        user_name = conn.getUser().getOmeName()
        owner_root = os.path.join(root, user_name)

        # check if the user has an HRM account (a folder with his/her name should already exist)
        if os.path.isdir(owner_root) or conn.getUser().isAdmin():
            for object_id in object_id_list:

                # search in all the user's group
                conn.SERVICE_OPTS.setOmeroGroup('-1')

                # get the object
                omero_object = conn.getObject(object_type, object_id)

                # check if that object exists
                if omero_object is not None:
                    # set the correct group Id
                    conn.SERVICE_OPTS.setOmeroGroup(omero_object.getDetails().getGroup().getId())

                    # select object type and add owner as key-value pair
                    if object_type == 'Image':
                        n_image += process_image(conn, omero_object, owner_root, download_existing_images)

                    if object_type == 'Dataset':
                        project = omero_object.getParent()
                        if project is None:
                            project_name = "None"
                        else:
                            project_name = "{}_{}".format(project.getId(), project.getName())
                        n_image_tmp, n_dataset_tmp = process_dataset(conn, omero_object, project_name, owner_root,
                                                                     download_existing_images)
                        n_dataset += n_dataset_tmp
                        n_image += n_image_tmp

                    if object_type == 'Project':
                        n_image_tmp, n_dataset_tmp, n_project_tmp = process_project(conn, omero_object, owner_root,
                                                                                    download_existing_images)
                        n_image += n_image_tmp
                        n_dataset += n_dataset_tmp
                        n_project += n_project_tmp
                else:
                    print(object_type, object_id, "does not exist or you do not have access to it")

            # build summary message    
            if not user_name == "":
                message = "Downloaded {} image(s), {} dataset(s), {} project(s) from {}".format(n_image, n_dataset,
                                                                                                n_project, user_name)
            else:
                message = "Cannot download objects"
            print(message)
        else:
            print("You don't have an active account on HRM. Please go on https://hrm-biop.epfl.ch/ and sign in to HRM")
            print("If you do not have any HRM account, please go on https://hrm-biop.epfl.ch/ and ask for an HRM account")
            message = f"Your HRM account ({user_name}) is not active. Please go on https://hrm-biop.epfl.ch/"
    else:
        message = "The root HRM folder doesn't exists. Please correct it."
        print(message)

    return message


def run_script():
    data_types = [rstring('Image'), rstring('Dataset'), rstring('Project')]
    client = scripts.client(
        'Send images to HRM deconvolution server',
        """
    This script sends all images from the selected source(s) to your HRM folder (\\sv-nas1.rcp.epfl.ch\ptbiop-raw\HRM-Share).
        """,
        scripts.String(
            DATA_TYPE_PARAM_NAME, optional=False, grouping="1",
            description="Choose source of images",
            values=data_types, default="Dataset"),

        scripts.List(
            ID_PARAM_NAME, optional=False, grouping="2",
            description="Object ID(s) or username(s).").ofType(rstring('')),

        scripts.Bool(
            OVERWRITE_PARAM_NAME, optional=False, grouping="3",
            description="Overwrite existing images on HRM", default=False),

        authors=["Rémy Dornier"],
        institutions=["EPFL - BIOP"],
        contact="omero@groupes.epfl.ch"
    )

    try:
        # process the list of args above.
        script_params = {}
        for key in client.getInputKeys():
            if client.getInput(key):
                script_params[key] = client.getInput(key, unwrap=True)

        # wrap client to use the Blitz Gateway
        conn = BlitzGateway(client_obj=client)
        print("script params")
        for k, v in script_params.items():
            print(k, v)
        message = download_images_for_hrm(conn, script_params)
        client.setOutput("Message", rstring(message))

    finally:
        client.closeSession()


if __name__ == "__main__":
    run_script()
