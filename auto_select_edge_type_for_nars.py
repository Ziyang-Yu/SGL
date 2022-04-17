from typing import Dict, List, Tuple
from functools import reduce
import heapq
import warnings
import time

import torch

from dataset.dblp import Dblp
from models.hetero_SGAP_models import NARS_SIGN, NARS_SIGN_WeightSharedAcrossFeatures,\
    NARS_SGC_WithLearnableWeights, Fast_NARS_SGC_WithLearnableWeights
from tasks.node_classification import HeteroNodeClassification
from auto_choose_gpu import GpuWithMaxFreeMem

# Hyperparameters
PROP_STEPS = 3
HIDDEN_DIM = 256
NUM_LAYERS = 2
NUM_EPOCHS_TO_TRAIN = 50
NUM_EPOCHS_TO_FIND_WEIGHT = 20
LR = 0.01
WEIGHT_DECAY = 0.0
BATCH_SIZE = 10000


def GenerateSubgraphsWithSameEdgeTypeNum(dataset, random_subgraph_num: int, subgraph_edge_type_num: int) -> Dict:
    return dataset.nars_preprocess(edge_types=dataset.EDGE_TYPES,
                                   predict_class=dataset.TYPE_OF_NODE_TO_PREDICT,
                                   random_subgraph_num=random_subgraph_num,
                                   subgraph_edge_type_num=subgraph_edge_type_num)


# Input format: [(random_subgraph_num, subgraph_edge_type_num), ...]
# Each element is a tuple of (random_subgraph_num, subgraph_edge_type_num)
def GenerateSubgraphDict(dataset, subgraph_config: List) -> Dict:
    subgraph_list = [GenerateSubgraphsWithSameEdgeTypeNum(
        dataset, random_subgraph_num, subgraph_edge_type_num)
        for random_subgraph_num, subgraph_edge_type_num
        in subgraph_config]

    return reduce(lambda x, y: {**x, **y}, subgraph_list)


def Dict2List(dict: Dict) -> List:
    return [(key, dict[key]) for key in dict]


# Input format: [(random_subgraph_num, subgraph_edge_type_num), ...]
# Each element is a tuple of (random_subgraph_num, subgraph_edge_type_num)
def GenerateSubgraphList(dataset, subgraph_config: List) -> List:
    return Dict2List(GenerateSubgraphDict(dataset, subgraph_config))


# Input format: [(random_subgraph_num, subgraph_edge_type_num), ...]
# Each element is a tuple of (random_subgraph_num, subgraph_edge_type_num)
def OneTrialWithSubgraphConfig(dataset, subgraph_config: List, num_epochs: int) -> Tuple[
        float, List, torch.torch.Tensor]:
    subgraph_list = GenerateSubgraphList(subgraph_config)

    predict_class = dataset.TYPE_OF_NODE_TO_PREDICT

    model = Fast_NARS_SGC_WithLearnableWeights(prop_steps=PROP_STEPS,
                                               feat_dim=dataset.data.num_features[predict_class],
                                               num_classes=dataset.data.num_classes[predict_class],
                                               hidden_dim=HIDDEN_DIM, num_layers=NUM_LAYERS,
                                               random_subgraph_num=len(subgraph_list))

    device = torch.device(
        f"cuda:{GpuWithMaxFreeMem()}" if torch.cuda.is_available() else "cpu")
    classification = HeteroNodeClassification(dataset, predict_class, model,
                                              lr=LR, weight_decay=WEIGHT_DECAY,
                                              epochs=num_epochs, device=device,
                                              train_batch_size=BATCH_SIZE,
                                              eval_batch_size=BATCH_SIZE,
                                              subgraph_list=subgraph_list,
                                              seed=int(time.time()))
    test_acc = classification.test_acc
    raw_weight = classification.subgraph_weight
    weight_sum = raw_weight.sum()
    normalized_weight = raw_weight/weight_sum

    return test_acc, subgraph_list, normalized_weight


def TopKIndex(k: int, tensor: torch.Tensor) -> List:
    return heapq.nlargest(k, range(tensor.size(0)), key=lambda i: tensor[i])


def OneTrialWithSubgraphList(dataset, subgraph_list: List, num_epochs: int) -> Tuple[
        float, List, torch.Tensor]:

    predict_class = dataset.TYPE_OF_NODE_TO_PREDICT
    model = Fast_NARS_SGC_WithLearnableWeights(prop_steps=PROP_STEPS,
                                               feat_dim=dataset.data.num_features[predict_class],
                                               num_classes=dataset.data.num_classes[predict_class],
                                               hidden_dim=HIDDEN_DIM, num_layers=NUM_LAYERS,
                                               random_subgraph_num=len(subgraph_list))

    device = torch.device(
        f"cuda:{GpuWithMaxFreeMem()}" if torch.cuda.is_available() else "cpu")
    classification = HeteroNodeClassification(dataset, predict_class, model,
                                              lr=LR, weight_decay=WEIGHT_DECAY,
                                              epochs=num_epochs, device=device,
                                              train_batch_size=BATCH_SIZE,
                                              eval_batch_size=BATCH_SIZE,
                                              subgraph_list=subgraph_list,
                                              seed=int(time.time()))

    test_acc = classification.test_acc
    raw_weight = classification.subgraph_weight
    weight_sum = raw_weight.sum()
    normalized_weight = raw_weight/weight_sum

    return test_acc, subgraph_list, normalized_weight


# Input format: [(random_subgraph_num, subgraph_edge_type_num), ...]
# Each element is a tuple of (random_subgraph_num, subgraph_edge_type_num)
# Only top k subgraphs with highest weights are retained
def OneTrialWithSubgraphListTopK(dataset, subgraph_config: List, k: int,
                                 num_epochs_to_find_weight: int, num_epochs_to_train: int) -> float:
    original_test_acc, subgraph_list, normalized_weight = OneTrialWithSubgraphConfig(
        dataset, subgraph_config, num_epochs_to_find_weight)
    if k < len(subgraph_list):
        k = len(subgraph_list)
        warnings.warn('k is larger than the number of subgraphs,'
                      'k is set to the number of subgraphs',
                      UserWarning)

    top_k_index = TopKIndex(k, normalized_weight.abs())
    retained_subgraph_list = [subgraph_list[i] for i in top_k_index]

    test_acc, _, _ = OneTrialWithSubgraphList(
        dataset, retained_subgraph_list, num_epochs_to_train)

    return test_acc, original_test_acc


def main():
    dataset = Dblp(root='.', path_of_zip='./dataset/DBLP_processed.zip')

    SUBGRAPH_CONFIG=[(1,1),(3,2),(3,3),(4,1)]
    test_acc, original_test_acc = OneTrialWithSubgraphListTopK(dataset,
                                                               SUBGRAPH_CONFIG, 2,
                                                               num_epochs_to_train=NUM_EPOCHS_TO_TRAIN,
                                                               num_epochs_to_find_weight=NUM_EPOCHS_TO_FIND_WEIGHT)

    print('test_acc:', test_acc)
    print('original_test_acc:', original_test_acc)


if __name__ == '__main__':
    main()
