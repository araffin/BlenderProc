import bpy
import os
from src.renderer.Renderer import Renderer
from src.utility.Utility import Utility
from src.utility.ColorPicker import get_colors, rgb_to_hex
from src.postprocessing.NoiseRemoval import NoiseRemoval
from src.utility.Config import Config
import imageio
import numpy as np


class SegMapRenderer(Renderer):

    def __init__(self, config):
        Renderer.__init__(self, config)

    # def scale_color(self, color):
    #     """ Maps color values to the range [0, 2^16], s.t. the space between the mapped colors is maximized.

    #     :param color: An integer representing the index of the color has to be in [0, "num_labels" - 1]
    #     :return: The integer representing the final color.
    #     """
    #     # 65536 = 2**16 the color depth, 32768 = 2**15 = 2**16/2
    #     return ((color * 65536) / (bpy.data.scenes["Scene"]["num_labels"])) + (32768 / (bpy.data.scenes["Scene"]["num_labels"]))

    def _get_idx(self,array,item):
        try:
            return array.index(item)
        except ValueError:
            return -1

    def color_obj(self, obj, color):
        """ Adjusts the materials of the given object, s.t. they are ready for rendering the seg map.

        This is done by replacing all nodes just with an emission node, which emits the color corresponding to the category of the object.

        :param obj: The object to use.
        :param color: RGB array of a color.
        """
        for m in obj.material_slots:
            nodes = m.material.node_tree.nodes
            links = m.material.node_tree.links
            emission_node = nodes.new(type='ShaderNodeEmission')
            output = nodes.get("Material Output")

            emission_node.inputs[0].default_value[:3] = [c/255 for c in color]
            links.new(emission_node.outputs[0], output.inputs[0])

    def run(self):
        """ Renders segmentation maps for each registered keypoint.

        The rendering is stored using the .exr filetype and a color depth of 16bit to achieve high precision.
        """
        with Utility.UndoAfterExecution():
            self._configure_renderer()
            NR = NoiseRemoval(self.config)

            # get current method for color mapping, instance or class
            method = self.config.get_string("map_by", "class") 
            
            if method == "class":
                # Generated colors for each class
                rgbs = get_colors(bpy.data.scenes["Scene"]["num_labels"])
                class_to_rgb = {}
                cur_idx = 0
            else:
                # Generated colors for each instance
                rgbs = get_colors(len(bpy.context.scene.objects))

            hexes = [rgb_to_hex(rgb) for rgb in rgbs]

            # Initialize maps
            color_map = []

            bpy.context.scene.render.image_settings.color_mode = "BW"
            bpy.context.scene.render.image_settings.file_format = "OPEN_EXR"
            bpy.context.scene.render.image_settings.color_depth = "16"
            bpy.context.view_layer.cycles.use_denoising = False
            bpy.data.scenes["Scene"].cycles.filter_width = 0.0
            
            for idx, obj in enumerate(bpy.context.scene.objects):
                
                # find color according to method given in config
                color_idx = -1 # current color doesnt exist in list of rgs
                rgb = [0,0,0] # initialize color

                # if class specified for this object or not
                if "category_id" in obj:
                    _class  = obj['category_id']
                else:
                    _class = None

                # if mehtod to assign color is by class or by instance
                if method == "class" and _class is not None: 
                    if _class not in class_to_rgb: # if class has not been assigned a color yet
                        class_to_rgb[_class] = {"rgb" : rgbs[cur_idx], "rgb_idx": cur_idx, _hex: rgb_to_hex(rgbs[cur_idx])} # assign the class with a color
                        cur_idx+=1 # set counter to next avialable color    
                    rgb = class_to_rgb[category_id]["rgb"] # assign this object the color of this class
                    color_idx = class_to_rgb[category_id]["rgb_idx"] # get idx of assigned color
                else:
                    rgb = rgbs[idx] # assign this object a color
                    color_idx = idx # each instance to color is one to one mapping, both have same idx
                
                # add values to a map
                color_map.append({'color':rgb, 'objname': obj.name, 'class': _class, 'idx': color_idx})

                self.color_obj(obj, rgb)
                     
            self._render("seg_")

            # After rendering
            for frame in range(bpy.context.scene.frame_start, bpy.context.scene.frame_end + 1): # for each rendered frame
                file_path = os.path.join(self.output_dir, "seg_" +  "%04d"%frame + ".exr")
                segmentation = imageio.imread(file_path)[:, :, :3]
                segmentation = np.round(segmentation * 255).astype(int)
                #segmentation = NR.run(segmentation) # remove noise (This is making each pixel equal to zero, need to debug it, however this part is not necessary for working)
                # for idx, row in enumerate(segmentation):
                #     #seg_hex.append([rgb_to_hex(rgb) for rgb in row])
                #     for rgb in row:
                #         if rgb[0] > 0 or rgb[1] > 0 or rgb[2] > 0:
                #             print(rgb)
                segmap = np.zeros(segmentation.shape[:2])# initialize mask

                for idx, row in enumerate(segmentation):
                    segmap[idx,:] = [self._get_idx(hexes,rgb_to_hex(rgb)) for rgb in row]
                fname = os.path.join(self.output_dir,"segmap_" + "%04d"%frame)
                np.save(fname,segmap)
                #np.save(os.path.join(self.output_dir,"segmentation_" + "%04d"%frame),segmentation)
            
            #np.save(os.path.join(self.output_dir,"rgbs"),rgbs)



        self._register_output("seg_", "seg", ".exr", "2.0.1")
        self._register_output("segmap_", "segmap", ".npy", "0.0.1")