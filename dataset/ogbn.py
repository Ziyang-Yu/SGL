import pickle as pkl
import os.path as osp
import torch
from ogb.nodeproppred import PygNodePropPredDataset
from torch_geometric.utils import to_undirected

from base import Graph
from dataset import NodeDataset
from utils import pkl_read_file


class Ogbn(NodeDataset):
    def __init__(self, name="arxiv", root="./", split="official"):
        if name not in ["arxiv", "products", "papars100m", "mag"]:
            raise ValueError("Dataset name not found!")
        super(Ogbn, self).__init__(root + "ogbn/", name)

        self._data = pkl_read_file(self.processed_file_paths)
        self._train_idx, self._val_idx, self._test_idx = self.__generate_split(split)

    @property
    def raw_file_paths(self):
        filepath = "ogbn_" + self._name + "/processed/geometric_data_processed.pt"
        return osp.join(self._raw_dir, filepath)

    @property
    def processed_file_paths(self):
        filename = "graph"
        return osp.join(self._processed_dir, "{}.{}".format(self._name, filename))

    def _download(self):
        dataset = PygNodePropPredDataset("ogbn-" + self._name, self._raw_dir)

    def _process(self):
        dataset = PygNodePropPredDataset("ogbn-" + self._name, self._raw_dir)

        data = dataset[0]
        features, labels = data.x, data.y.to(torch.long).squeeze(1)
        num_node = data.num_nodes
        if self._name == "products":
            node_type = "product"
        else:
            node_type = "paper"

        undi_edge_index = to_undirected(data.edge_index, num_nodes=num_node)
        row, col = undi_edge_index
        edge_weight = torch.ones(len(row))
        if self._name == "products":
            edge_type = "product_together_product"
        else:
            edge_type = "paper_cite_paper"

        g = Graph(row, col, edge_weight, num_node, node_type, edge_type, x=features, y=labels)
        with open(self.processed_file_paths, 'wb') as rf:
            try:
                pkl.dump(g, rf)
            except IOError as e:
                print(e)
                exit(1)

    def __generate_split(self, split):
        if split == "official":
            dataset = PygNodePropPredDataset("ogbn-" + self._name, self._raw_dir)
            split_idx = dataset.get_idx_split()
            train_idx, val_idx, test_idx = split_idx['train'], split_idx['valid'], split_idx['test']
        elif split == "random":
            raise NotImplementedError
        else:
            raise ValueError("Please input valid split pattern!")

        return train_idx, val_idx, test_idx


# test
# dataset = Ogbn(name="arxiv", root="./")
