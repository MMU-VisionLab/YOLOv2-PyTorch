'''
YOLOv2 requires the label for each image to be in a particular format. 
Anchors are placed consistently all over the image based on the subsampled size (the final feature map size). E.g. a 320 x 320 image with a 
subsampling ratio of 32 will have a feature map of size 10 x 10. Anchors are placed on each of this 10 x 10 grid but the center coordinates, width and
height of the anchors are referenced to the original image. Therefore, the center or anchors are placed with a gap of 32 pixels horizontally and 
vertically on the original 320 x 320 image. We need to identify which grid (on the feature map) does the ground-truth bounding box's center falls into.
Then we compare the IoU between the ground-truth box and every anchor that belongs to the particular grid. Whichever anchor that has the highest IoU
with the ground-truth box will be responsible for detecting the object. NOTE: When we visualize the grids on the feature map, the anchors are located
on the intersection of the grids, NOT inside the grid.

Each anchor has 5 elements. Probability of objectness, center x, center y, width and height. The neural network will be forced to learn the probability
of objectness on each anchor and if the probability is above a certain threshold, the neural network will predict the offset of the anchor from
the ground-truth bounding box. However, the offset is not as simple as calculating the difference between the anchor box and the ground-truth box.
In order to maintain the model's stability, we will normalize both the anchor box and the ground-truth box based on the grid-cell's width and height so
that the center coordinates and height & width of both of the boxes falls in the range of 0 and 1. From there, we calculate the difference between
the value the model should predict (tx, ty) and the anchor box's center values to get the bounding box's center values. For the width and height,
refer to the YOLOv2 paper for the formula. Since the objectness probablity and center coordinates offset that the model should predict is from 0 to 1,
we will be using sigmoid activation function for them. However, the offset values for width and height can be a value from -1 to 1 (maybe TanH ? 
The paper does not state the activation function that should be used for this). 
'''


import math
import numpy as np 


def get_highest_iou_anchor(anchors, gt_box):
    '''
    Calculates the IoU between all the anchors and one ground-truth box.
    Returns the index of the anchor with the highest IoU provided the anchor has not been assigned with an object already. Else the next anchor
    with the highest IoU will be returned.
    '''

    x = np.minimum(anchors[:, -2], gt_box[2])
    y = np.minimum(anchors[:, -1], gt_box[3])

    if np.count_nonzero(x == 0) > 0 or np.count_nonzero(y == 0) > 0:
        raise ValueError ('The given box has no area!')

    intersection_area   = x*y 
    gt_box_area         = gt_box[2] * gt_box[3]
    anchors_area        = anchors[:, -2] * anchors[:, -1]

    IoUs = intersection_area/ (gt_box_area + anchors_area - intersection_area)

    highest_ious = np.argpartition(IoUs, -1) #get the sorted indexes.

    #we need to find the anchor with the next highest IoU if the current found anchor is already associated with a ground-truth box.
    index = 0
    current_highest = highest_ious[index]
    while (int(anchors[current_highest][0]) != 0 ): #iterate as long as the selected anchor is occupied.
        index += 1
        current_highest = highest_ious[index] #choose the next highest IoU anchor.

        #in the event of all anchors being occupied, the first anchor with the highest IoU will be chosen.
        if index == len(anchors): #stop the loop once all anchors are considered. 
            current_highest = highest_ious[0]
            break
    
    return current_highest
    



def label_formatting(gt_class_labels, gt_boxes, anchors_list, subsampled_ratio, resized_image_size, classes):
    '''
    Formats the given labels from the xml file into YOLO's format as explained above.
    '''
    
    subsampled_size = int(resized_image_size/subsampled_ratio)

    num_of_classes = len(classes)

    #this array will be used to store the ground truth probability of objectness and the offset calculations between the responsible anchors
    #and the ground-truth boxes. Hence the similarity of the shape of this array with the anchor lists array.
    regression_objectness_array = np.zeros((subsampled_size, subsampled_size, anchors_list.shape[-2], 5), dtype=np.float32)

    #this array will be used to store the class of the present objects in the responsible anchors.
    class_label_array = np.zeros((subsampled_size, subsampled_size, anchors_list.shape[-2], num_of_classes), dtype=np.float32)

    
    #An image can contain more than 1 objects.
    for i in range(gt_boxes.shape[0]):

        class_label_index = gt_class_labels[i] #extract the class index

        #extract the coordinate of the ground truth box. This ground-truth box's format is [x1,y1,x2,y2]

        gt_box_x1 = gt_boxes[i][0]
        gt_box_y1 = gt_boxes[i][1]
        gt_box_x2 = gt_boxes[i][2]
        gt_box_y2 = gt_boxes[i][3]

        #transform the ground truth values to [x,y,w,h] (center coordinates, width and height)
        gt_box_height = gt_box_y2 - gt_box_y1
        gt_box_width  = gt_box_x2 - gt_box_x1
        gt_center_x   = gt_box_x1 + (gt_box_width/2)
        gt_center_y   = gt_box_y1 + (gt_box_height/2)

        gt_box = [gt_center_x, gt_center_y, gt_box_width, gt_box_height]

        #identify the grid that holds the center of the ground truth box in the subsampled feature image.
        responsible_grid = [int(gt_center_x/subsampled_ratio), int(gt_center_y/subsampled_ratio)]

        #these are the anchors from the responsible grid that we calculate the IoU with.
        prospect_anchors = anchors_list[responsible_grid[0]][responsible_grid[1]]

        #get the index of the anchor from the responsible grid with the highest IoU.
        chosen_anchor_index = get_highest_iou_anchor(anchors=prospect_anchors, gt_box=gt_box)

        chosen_anchor = prospect_anchors[chosen_anchor_index] #the chosen anchor. [pr(obj), x, y, w, h]

        #CALCULATION FOR THE REGRESSION VALUES!
        #All anchors' center are located on the intersections of the grids. Therefore, we can calculate the offset of the ground-truth bounding box
        #using the responsible grid's location. Refer to the paper for more information.

        #as for the centers, the network must predict a value such that when the value is added to the responsible grid's coordinate, we get the
        #normalized value of the ground truth box's center.
        sigmoid_tx = gt_center_x/subsampled_ratio - responsible_grid[0]
        sigmoid_ty = gt_center_y/subsampled_ratio - responsible_grid[1]

        #as for the width and height, the network must predict the exponential value to the euler's number multiplied with anchor box's
        #width and height.
        tw = math.log(gt_box_width/chosen_anchor[3])
        th = math.log(gt_box_height/chosen_anchor[4])

        #objectness probability + regression values
        regression_values = np.asarray([1.0, sigmoid_tx, sigmoid_ty, tw, th], dtype=np.float32)

        #We need to occupy the probability of objnectness and the regression values in the chosen anchor's index.
        regression_objectness_array[responsible_grid[0]][responsible_grid[1]][chosen_anchor_index] = regression_values

        #mark the class of the object 
        class_label_array[responsible_grid[0]][responsible_grid[1]][chosen_anchor_index][class_label_index] = 1.0

    return regression_objectness_array, class_label_array