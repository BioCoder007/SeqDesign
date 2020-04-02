#!/usr/bin/env python3
import tensorflow as tf
import numpy as np
import argparse
import time
import sys
import os
import glob
if os.path.exists('/n/groups/marks/'):
    working_dir = f'/n/groups/marks/projects/autoregressive/v3'
else:
    working_dir = '..'
sys.path.append(working_dir)
import SeqDesign.hyper_conv_auto as model
from SeqDesign import helper
from SeqDesign import utils
from SeqDesign import aws_utils

parser = argparse.ArgumentParser(description="Calculate the log probability of mutated sequences.")
parser.add_argument("--channels", type=int, default=48, metavar='C', help="Number of channels.")
parser.add_argument("--r-seed", type=int, default=-1, metavar='RSEED', help="Random seed.")
parser.add_argument("--num-samples", type=int, default=1, metavar='N', help="Number of iterations to run the model.")
parser.add_argument("--minibatch-size", type=int, default=100, metavar='B', help="Minibatch size for inferring effect prediction.")
parser.add_argument("--dropout-p", type=float, default=1., metavar='P', help="Dropout p while sampling log p(x).")
parser.add_argument("--sess", type=str, default='', help="Session folder name for restoring a model.", required=True)
parser.add_argument("--checkpoint", type=int, default=250000,  metavar='CKPT', help="Checkpoint step number.", required=True)
parser.add_argument("--input", type=str, default='',  help="Directory and filename of the input data.", required=True)
parser.add_argument("--output", type=str, default='',  help="Directory and filename of the outout data.", required=True)
parser.add_argument("--alphabet-type", type=str, default='protein', metavar='T',  help="Alphabet to use for the dataset.", required=False)

ARGS = parser.parse_args()

print(ARGS)

print("OS: ", sys.platform)
print("Python: ", sys.version)
print("TensorFlow: ", tf.__version__)
print("Numpy: ", np.__version__)

available_devices = utils.get_available_gpus()
if available_devices:
    print('\t'.join(available_devices))
    print('\t'.join(utils.get_available_gpus_desc()))
    print(utils.get_cuda_version())
    print("CuDNN Version ", utils.get_cudnn_version())

print("SeqDesign git hash:", str(utils.get_github_head_hash()))
print()

data_helper = helper.DataHelperSingleFamily(working_dir=working_dir, alphabet_type=ARGS.alphabet_type)

# Variables for runtime modification
minibatch_size = ARGS.minibatch_size
alphabet_list = list(data_helper.alphabet)

sess_name = ARGS.sess
input_filename = ARGS.input
output_filename = ARGS.output

data_helper.read_in_test_data(input_filename)
print("Read in test data.")

if not glob.glob(f"{working_dir}/sess/{sess_name}/{sess_name}.ckpt-{ARGS.checkpoint}*"):
    if not aws_utils.aws_s3_get_file_grep(
        f'sess/{sess_name}',
        f'{working_dir}/sess/{sess_name}',
        f'{sess_name}.ckpt-{ARGS.checkpoint}.*',
    ):
        raise Exception("Could not download session files from S3.")

conv_model = model.AutoregressiveFR(dims={'alphabet': len(data_helper.alphabet)}, channels=ARGS.channels)

params = tf.trainable_variables()
p_counts = [np.prod(v.get_shape().as_list()) for v in params]
p_total = sum(p_counts)
print("Total parameter number:", p_total, "\n")

saver = tf.train.Saver()

# with tf.Session(config=cfg) as sess:
with tf.Session() as sess:

    # Initialization
    print('Initializing variables')
    init = tf.global_variables_initializer()
    sess.run(init)

    sess_namedir = f"{working_dir}/sess/{sess_name}/{sess_name}.ckpt-{ARGS.checkpoint}"
    saver.restore(sess, sess_namedir)
    print("Loaded parameters.")

    os.makedirs(output_filename.rsplit('/', 1)[0], exist_ok=True)
    data_helper.output_log_probs(
        sess, conv_model, output_filename,
        ARGS.num_samples, ARGS.dropout_p, ARGS.r_seed,
        ARGS.channels, minibatch_size=minibatch_size,
    )
    print("Done!")

if output_filename.startswith('output/'):
    aws_utils.aws_s3_cp(
        local_file=output_filename,
        s3_file=f'calc_logprobs/output/{output_filename.rsplit("/", 1)[1]}',
        destination='s3'
    )
