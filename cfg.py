import glob

data_images_path     = '../VOCdevkit/VOC2012/JPEGImages'
data_annotation_path = '../VOCdevkit/VOC2012/Annotations'
trained_model_path = './trained_model/'
image_sizes = [320,352,384,416,448,480,512,544,570,608]
image_depth  = 3
detection_conv_size = 3
subsampled_ratio = 32


#Get the image and annotation file paths
list_images      = sorted([x for x in glob.glob(data_images_path + '/**')])     #length : 17125
list_annotations = sorted([x for x in glob.glob(data_annotation_path + '/**')]) #length : 17125
total_images = len(list_images)


