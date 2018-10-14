from argparse import ArgumentParser, Namespace
import os
from tempfile import TemporaryDirectory
from typing import Union

import torch


def float_or_int(value: Union[float, int]) -> Union[float, int]:
    return float(value) if '.' in value else int(value)


def get_parser():
    """Builds an argument parser"""
    parser = ArgumentParser()

    # General arguments
    parser.add_argument('--data_path', type=str,
                        help='Path to data CSV file')
    parser.add_argument('--vocab_path', type=str,
                        help='Path to .vocab file if using jtnn')
    parser.add_argument('--save_dir', type=str, default=None,
                        help='Directory where model checkpoints will be saved')
    parser.add_argument('--checkpoint_dir', type=str, default=None,
                        help='Directory from which to load model checkpoints'
                             '(walks directory and ensembles all models that are found)')
    parser.add_argument('--dataset_type', type=str, choices=['classification', 'regression', 'regression_with_binning'],
                        help='Type of dataset, i.e. classification (cls) or regression (reg).'
                             'This determines the loss function used during training.')
    parser.add_argument('--num_bins', type=int, default=20,
                        help='Number of bins for regression with binning')
    parser.add_argument('--num_chunks', type=int, default=1,
                        help='Specify > 1 if your dataset is really big')
    parser.add_argument('--chunk_temp_dir', type=str, default='temp_chunks',
                        help='temp dir to store chunks in')
    parser.add_argument('--memoize_chunks', action='store_true', default=False,
                        help='store memo dicts for mol2graph in chunk_temp_dir when chunking, at large disk space cost')
    parser.add_argument('--separate_test_set', type=str,
                        help='Path to separate test set, optional')
    parser.add_argument('--metric', type=str, default=None, choices=['auc', 'prc-auc', 'rmse', 'mae', 'r2', 'accuracy'],
                        help='Metric to use during evaluation.'
                             'Note: Does NOT affect loss function used during training'
                             '(loss is determined by the `dataset_type` argument).'
                             'Note: Defaults to "auc" for classification and "rmse" for regression.')
    parser.add_argument('--seed', type=int, default=0,
                        help='Random seed to use when splitting data into train/val/test sets.'
                             'When `num_folds` > 1, the first fold uses this seed and all'
                             'subsequent folds add 1 to the seed.')
    parser.add_argument('--split_sizes', type=float, nargs=3, default=[0.8, 0.1, 0.1],
                        help='Split proportions for train/validation/test sets')
    parser.add_argument('--num_folds', type=int, default=1,
                        help='Number of folds when performing cross validation')
    parser.add_argument('--quiet', action='store_true', default=False,
                        help='Skip non-essential print statements')
    parser.add_argument('--log_frequency', type=int, default=10,
                        help='The number of batches between each logging of the training loss')
    parser.add_argument('--no_cuda', action='store_true', default=False,
                        help='Turn off cuda')
    parser.add_argument('--show_individual_scores', action='store_true', default=False,
                        help='Show all scores for individual targets, not just average, at the end')
    parser.add_argument('--labels_to_show', type=str,
                        help='List of targets to show individual scores for, if specified')

    # Training arguments
    parser.add_argument('--epochs', type=int, default=30,
                        help='Number of epochs to run')
    parser.add_argument('--batch_size', type=int, default=50,
                        help='Batch size')
    parser.add_argument('--truncate_outliers', action='store_true', default=False,
                        help='Truncates outliers in the training set to improve training stability'
                             '(All values outside mean ± 3 * std are truncated to equal mean ± 3 * std)')
    parser.add_argument('--warmup_epochs', type=float_or_int, default=2,
                        help='Number of epochs during which learning rate increases linearly from'
                             'init_lr to max_lr. Afterwards, learning rate decreases exponentially'
                             'from max_lr to final_lr.')
    parser.add_argument('--init_lr', type=float, default=1e-4,
                        help='Initial learning rate')
    parser.add_argument('--max_lr', type=float, default=1e-3,
                        help='Maximum learning rate')
    parser.add_argument('--final_lr', type=float, default=1e-4,
                        help='Final learning rate')
    parser.add_argument('--max_grad_norm', type=float, default=None,
                        help='Maximum gradient norm when performing gradient clipping')

    # Model arguments
    parser.add_argument('--ensemble_size', type=int, default=1,
                        help='Number of models in ensemble')
    parser.add_argument('--hidden_size', type=int, default=300,
                        help='Dimensionality of hidden layers in MPN')
    parser.add_argument('--bias', action='store_true', default=False,
                        help='Whether to add bias to linear layers')
    parser.add_argument('--depth', type=int, default=3,
                        help='Number of message passing steps')
    parser.add_argument('--layer_norm', action='store_true', default=False,
                        help='Add layer norm after each message passing step')
    parser.add_argument('--dropout', type=float, default=0.0,
                        help='Dropout probability')
    parser.add_argument('--activation', type=str, default='ReLU', choices=['ReLU', 'LeakyReLU', 'PReLU', 'tanh'],
                        help='Activation function')
    parser.add_argument('--attention', action='store_true', default=False,
                        help='Perform self attention over the atoms in a molecule')
    parser.add_argument('--message_attention', action='store_true', default=False,
                        help='Perform attention over messages.')
    parser.add_argument('--global_attention', action='store_true', default=False,
                        help='True to perform global attention across all messages on each message passing step')
    parser.add_argument('--message_attention_heads', type=int, default=1,
                        help='Number of heads to use for message attention')
    parser.add_argument('--master_node', action='store_true', default=False,
                        help='Add a master node to exchange information more easily')
    parser.add_argument('--master_dim', type=int, default=600,
                        help='Number of dimensions for master node state')
    parser.add_argument('--use_master_as_output', action='store_true', default=False,
                        help='Use master node state as output')
    parser.add_argument('--addHs', action='store_true', default=False,
                        help='Explicitly adds hydrogens to the molecular graph')
    parser.add_argument('--three_d', action='store_true', default=False,
                        help='Adds 3D coordinates to atom and bond features')
    parser.add_argument('--virtual_edges', action='store_true', default=False,
                        help='Adds virtual edges between non-bonded atoms')
    parser.add_argument('--drop_virtual_edges', action='store_true', default=False,
                        help='Randomly drops O(n_atoms) virtual edges so O(n_atoms) edges total instead of O(n_atoms^2)')
    parser.add_argument('--deepset', action='store_true', default=False,
                        help='Modify readout function to perform a Deep Sets set operation using linear layers')
    parser.add_argument('--set2set', action='store_true', default=False,
                        help='Modify readout function to perform a set2set operation using an RNN')
    parser.add_argument('--set2set_iters', type=int, default=3,
                        help='Number of set2set RNN iterations to perform')
    parser.add_argument('--jtnn', action='store_true', default=False,
                        help='Build junction tree and perform message passing over both original graph and tree')

    return parser


def modify_args(args: Namespace):
    """Modifies and validates arguments"""
    global temp_dir  # Prevents the temporary directory from being deleted upon function return

    # Argument modification/checking
    if args.save_dir is not None:
        os.makedirs(args.save_dir, exist_ok=True)
    else:
        temp_dir = TemporaryDirectory()
        args.save_dir = temp_dir.name

    args.cuda = not args.no_cuda and torch.cuda.is_available()
    del args.no_cuda

    if args.metric is None:
        args.metric = 'auc' if args.dataset_type == 'classification' else 'rmse'

    if not (args.dataset_type == 'classification' and args.metric in ['auc', 'prc-auc', 'accuracy'] or
            (args.dataset_type == 'regression' or args.dataset_type == 'regression_with_binning') and args.metric in ['rmse', 'mae', 'r2']):
        raise ValueError('Metric "{}" invalid for dataset type "{}".'.format(args.metric, args.dataset_type))

    args.minimize_score = args.metric in ['rmse', 'mae']

    if args.checkpoint_dir is not None:
        args.checkpoint_paths = []

        for root, _, files in os.walk(args.checkpoint_dir):
            for fname in files:
                if fname == 'model.pt':
                    args.checkpoint_paths.append(os.path.join(root, fname))

        args.ensemble_size = len(args.checkpoint_paths)
    else:
        args.checkpoint_paths = None


def parse_args():
    """Parses arguments (includes modifying/validating arguments)"""
    parser = get_parser()
    args = parser.parse_args()
    modify_args(args)

    return args
