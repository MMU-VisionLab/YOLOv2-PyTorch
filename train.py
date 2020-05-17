'''
ImageNet and YOLO model training.
'''
import itertools
import os
from random import randint
import torch
import numpy as np
from tqdm import tqdm
from torch.utils.data import DataLoader
from load_data import LoadDataset, ToTensor, ImgnetLoadDataset
import cfg
from yolo_net import YOLO, OPTIMIZER, LR_DECAY, loss #decay rate update
from post_process import PostProcess
from darknet19 import DARKNET19, IMGNET_OPTIMIZER, IMGNET_LR_DECAY, IMGNET_CRITERION, calculate_accuracy
from utils import calculate_map


if not cfg.IMGNET_MODEL_PRESENCE:
    '''
    If the classification model is not present, then we'll have to train the model with the ImageNet images for classification.
    '''
    print(DARKNET19)

    IMGNET_TRAINING_DATA = ImgnetLoadDataset(resized_image_size=cfg.IMGNET_IMAGE_SIZE, class_list=cfg.IMGNET_CLASSES,
                                             dataset_folder_path=cfg.IMGNET_DATASET_PATH, transform=ToTensor())

    IMGNET_DATALOADER = DataLoader(IMGNET_TRAINING_DATA, batch_size=cfg.IMGNET_BATCH_SIZE, shuffle=True, num_workers=4)

    best_accuracy = 0
    for epoch_idx in range(cfg.IMGNET_TOTAL_EPOCH):

        epoch_training_loss = []
        epoch_accuracy = []

        for i, sample in tqdm(enumerate(IMGNET_DATALOADER)):

            batch_x, batch_y = sample["image"].cuda(), sample["label"].type(torch.long).cuda()

            IMGNET_OPTIMIZER.zero_grad()

            classification_output = DARKNET19(batch_x)

            training_loss = IMGNET_CRITERION(input=classification_output, target=batch_y)

            epoch_training_loss.append(training_loss.item())

            training_loss.backward()
            IMGNET_OPTIMIZER.step()

            batch_acc = calculate_accuracy(network_output=classification_output, target=batch_y)
            epoch_accuracy.append(batch_acc.item())


        IMGNET_LR_DECAY.step()

        current_accuracy = np.average(epoch_accuracy)
        print("Epoch %d, \t Training Loss : %g, \t Training Accuracy : %g"%(epoch_idx, np.average(epoch_training_loss), current_accuracy))

        if current_accuracy > best_accuracy:
            best_accuracy = current_accuracy
            torch.save(DARKNET19.state_dict(), cfg.IMGNET_MODEL_SAVE_PATH_FOLDER+cfg.IMGNET_MODEL_SAVE_NAME)


#Transfer Learning
IMGNET_MODELLOAD = torch.load(cfg.IMGNET_MODEL_SAVE_PATH_FOLDER+cfg.IMGNET_MODEL_SAVE_NAME)
ALL_KEYS = IMGNET_MODELLOAD.keys()
TOTAL_KEYS = len(ALL_KEYS)

#exclude the last 2 keys (the classification layer's weight and bias)
TRANSFER_LEARNING_PARAMS = dict(itertools.islice(IMGNET_MODELLOAD.items(), TOTAL_KEYS-2))

YOLO.load_state_dict(TRANSFER_LEARNING_PARAMS, strict=False)

if os.path.exists('./yolo_model.pth'):

    YOLO_PARAMS = torch.load('./yolo_model.pth')
    YOLO.load_state_dict(YOLO_PARAMS)
    print("YOLO loaded!")

print(YOLO)

HIGHEST_MAP = 0

training_losses_list = []
training_maps_list = []

for epoch_idx in range(cfg.TOTAL_EPOCH):

    epoch_loss = 0
    training_loss = []


    if epoch_idx % 10 == 0:
        #there are 10 options for image sizes.
        chosen_image_index = randint(0, 9)

    chosen_image_size = cfg.IMAGE_SIZES[chosen_image_index]
    feature_size = int(chosen_image_size/cfg.SUBSAMPLED_RATIO)

    training_data = LoadDataset(resized_image_size=chosen_image_size, transform=ToTensor())

    dataloader = DataLoader(training_data, batch_size=cfg.BATCH_SIZE, shuffle=True, num_workers=4)

    postProcess_obj = PostProcess(box_num_per_grid=cfg.K, feature_size=feature_size, anchors_list=training_data.anchors_list)

    for i, sample in tqdm(enumerate(dataloader)):
        # print(sample["image"].shape)
        # print(sample["label"].shape)

        batch_x, batch_y = sample["image"].cuda(), sample["label"].cuda()

        OPTIMIZER.zero_grad()

        #[batch size, feature map width, feature map height, number of anchors, 5 + number of classes]
        outputs = YOLO(batch_x) #THE OUTPUTS ARE NOT YET GONE THROUGH THE ACTIVATION FUNCTIONS.

        total_loss = loss(predicted_array=outputs, label_array=batch_y)

        #Suppress the prediction outputs.
        nms_output = postProcess_obj.nms(predictions=outputs.detach().clone().contiguous())

        #collect every mini-batch prediction and ground truth arrays.
        postProcess_obj.collect(network_output=nms_output.clone(), ground_truth=batch_y.clone())

        training_loss.append(total_loss.item())
        total_loss.backward()
        OPTIMIZER.step()



    postProcess_obj.clear_lists()
    LR_DECAY.step() #decay rate update

    training_loss = np.average(training_loss)
    print("Epoch %d, \t Loss : %g"%(epoch_idx, training_loss))

    training_losses_list.append(training_loss)

    #calculate mean
    if epoch_idx % 10 == 0:

        avg_prec = postProcess_obj.calculate_ap()
        mean_ap = calculate_map(avg_prec)
        postProcess_obj.clear_lists()
        print("Mean AP : ", mean_ap)
        training_maps_list.append(mean_ap)
        if mean_ap > highest_map:
            highest_map = mean_ap
            torch.save(YOLO.state_dict(), './yolo_model.pth')


AP_FILE = open("map.txt", 'w+')
AP_FILE.write(str(training_maps_list))
AP_FILE.close()

LOSS_FILE = open("loss.txt", "w+")
LOSS_FILE.write(str(training_losses_list))
LOSS_FILE.close()
