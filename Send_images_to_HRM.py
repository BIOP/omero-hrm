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

from omero.gateway import BlitzGateway
import omero.scripts as scripts
import os
from omero.rtypes import rstring
from omero_model_OriginalFileI import OriginalFileI


DATA_TYPE_PARAM_NAME = "Data_Type"
OVERWRITE_PARAM_NAME = "Overwrite_images_on_HRM"
ID_PARAM_NAME = "IDs"


def download_image(conn, target_obj, path, download_existing_images):
    """
    Download an image to the given path
    return downloading status
    """
    # Download the files composing the image
    fset = target_obj.getFileset()

    if not fset:
        print("ERROR", f"ERROR: no original file(s) for [{target_obj.getId()}] found!")
        return False

    downloads = []
    # assemble a list of items to download
    for fset_file in fset.listFiles():
        file_name = fset_file.getName()
        file_path = fset_file.getPath()

        if download_existing_images or not os.path.exists(os.path.join(path, file_name)):
            downloads.append((fset_file.getId(), os.path.join(path, file_name)))
        else:
            print(f"INFO: {file_name} already exists in {path}")

    # now initiate the downloads for all original files:
    for (file_id, tgt) in downloads:
        try:
            print(f"Downloading original file [{file_id}] to [{tgt}]...")
            conn.c.download(OriginalFileI(file_id), tgt)
        except Exception as err:  # pylint: disable-msg=broad-except
            print("ERROR", f"ERROR: downloading {file_id} to '{tgt}' failed: {err}")
            return False
        print("SUCCESS", f"ID {file_id} downloaded as '{os.path.basename(tgt)}'")
    return True


def build_path(root, project_name, dataset_name):
    """
    Build an omero-like and HRM compatible path (Raw/omero/project/dataset/image)
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
    root = "/mnt/hrmshare"  # script_params["HRM_path"]
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
                ''' # Remove Admin part because not necessary
                if not omero_object == None:
                    if(conn.getUser().isAdmin()):
                        # get sudo connection
                        user_name = omero_object.getOwner().getOmeName()
                        user_conn = conn.suConn(user_name)
                        user_conn.SERVICE_OPTS.setOmeroGroup('-1')
                        omero_object = user_conn.getObject(object_type, object_id)
                        owerRoot = os.path.join(root, user_name)
                    else:
                        user_conn = conn
                '''

                # check if that object exists
                if not omero_object is None:
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

                    '''
                    # close the user connection                
                    if(conn.getUser().isAdmin()):
                        user_conn.close()
                    '''

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
    This script sends all images from the selected source(s) to your HRM folder (\\sv-nas1.rcp.epfl.ch\ptbiop-raw\public\HRM-Share).
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
