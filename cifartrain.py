import tensorflow as tf
import numpy as np
import pickle
import time


EPOCHS = 10
BATCH_SIZE = 64
LEARNING_RATE = 0.001
IMAGE_SIZE = 32
IMAGE_DEPTH = 3
TRAIN_SIZE = 40000
EPOCH_SIZE = TRAIN_SIZE // BATCH_SIZE
HALF_EPOCH_SIZE = EPOCH_SIZE // 2


class Data:
    # Train and Test Data Layout
    # Dictionary with following keys
    # 'batch_label' - Gives the batch id the training data belongs to
    # 'coarse_labels' - 50000 labels of class names (1 .. 20)
    # 'data' - 50000 image data of type
    #           <0, 1, ...., 1023> R-Channel,
    #           <1024, 1025, ..., 2047> G-Channel,
    #           <2048, 2049, ..., 3071> B-Channel
    # 'fine_labels' - 50000 labels of class names (1...100)
    # 'filenames' - 50000 filenames

    def __init__(self, file):
        def unpickle(file):
            with open(file, 'rb') as fo:
                dict = pickle.load(fo, encoding='bytes')
            return dict

        self.raw = unpickle('data/' + file)

        self.batch_label = None
        self.coarse_labels = None
        self.fine_labels = None
        self.data = None
        self.filenames = None
        self.num_data = 0

        self.reset_data()

    def reset_data(self):
        self.batch_label = self.raw[b'batch_label']
        self.coarse_labels = np.array(self.raw[b'coarse_labels'])
        self.fine_labels = np.array(self.raw[b'fine_labels'])
        self.data = self.raw[b'data']
        self.filenames = self.raw[b'filenames']
        self.num_data = len(self.data)

    def select(self, start=0, finish=-1):
        self.batch_label = self.batch_label[start:finish]
        self.coarse_labels = self.coarse_labels[start:finish]
        self.fine_labels = self.fine_labels[start:finish]
        self.data = self.data[start:finish]
        self.filenames = self.filenames[start:finish]
        self.num_data = len(self.data)


train = Data('train')
validation = Data('train')
test = Data('test')

# Step 1: Data Selection: Select 40000 examples
train.select(finish=TRAIN_SIZE)
validation.select(start=TRAIN_SIZE)

# Step 2: Augment Data

# Step 3: Pre-process / Normalize data

# Step 4: Build NN architecture


def create_conv_layer(num, inputs, filters, size=5, stride=1):
    layer_name = 'Conv' + str(num) + '-' + str(size) + 'x' + str(size) + 'x' + str(filters) + '-' + str(stride)

    return tf.layers.conv2d(inputs=inputs,
                            filters=filters,
                            kernel_size=[size, size],
                            strides=[stride, stride],
                            activation=tf.nn.relu,
                            kernel_initializer=tf.contrib.layers.xavier_initializer(),
                            bias_initializer=tf.contrib.layers.xavier_initializer(),
                            name=layer_name)


def create_pooling_layer(num, inputs, size=2, stride=2):
    layer_name = 'Pool' + str(num) + '-' + str(size) + 'x' + str(size) + '-' + str(stride)
    return tf.layers.max_pooling2d(inputs=inputs,
                                   pool_size=[size, size],
                                   strides=[stride, stride],
                                   name=layer_name)


def create_dense_layer(num, inputs, nodes, activation=tf.nn.relu):
    layer_name = 'Dense' + str(num) + '-' + str(nodes)
    if num < 0:
        layer_name = 'Output'
    return tf.layers.dense(inputs=inputs,
                           units=nodes,
                           activation=activation,
                           kernel_initializer=tf.contrib.layers.xavier_initializer(),
                           bias_initializer=tf.contrib.layers.xavier_initializer(),
                           name=layer_name)


# Step 4.0: Prep Data
data_x = tf.placeholder(tf.uint8, name='Features')
data_y = tf.placeholder(tf.int64, name='Labels')
raw_input = tf.data.Dataset.from_tensor_slices((data_x, data_y))

dataset = raw_input.repeat(count=EPOCHS).batch(batch_size=BATCH_SIZE)
input_iter = dataset.make_initializable_iterator()

data_batch, label_batch = input_iter.get_next()
data_batch_cast = tf.cast(data_batch, tf.float32)

# Step 4.1: Build Architecture
input_layer = tf.reshape(data_batch_cast, [-1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_DEPTH])


first_convolution_layer = create_conv_layer(num=1,
                                            inputs=input_layer,
                                            filters=6)

first_pooling_layer = create_pooling_layer(num=1,
                                           inputs=first_convolution_layer)

second_convolution_layer = create_conv_layer(num=2,
                                             inputs=first_pooling_layer,
                                             filters=6)

second_pooling_layer = create_pooling_layer(num=1,
                                            inputs=second_convolution_layer)

flattened_pooling_layer = tf.layers.flatten(inputs=second_pooling_layer,
                                            name='FlattenPool2')

first_dense_layer = create_dense_layer(num=1,
                                       inputs=flattened_pooling_layer,
                                       nodes=120)

second_dense_layer = create_dense_layer(num=2,
                                        inputs=first_dense_layer,
                                        nodes=84)

logits = create_dense_layer(num=3,
                            inputs=second_dense_layer,
                            nodes=100)


loss_op = tf.losses.sparse_softmax_cross_entropy(labels=label_batch,
                                                 logits=logits)
tf.summary.scalar(name='Loss',
                  tensor=loss_op)

train_step = tf.train.AdamOptimizer(learning_rate=LEARNING_RATE).minimize(loss_op)


prediction_op = tf.equal(tf.argmax(input=logits, axis=1), label_batch)
accuracy_op = tf.reduce_mean(tf.cast(x=prediction_op, dtype=tf.float32))
tf.summary.scalar(name='Accuracy',
                  tensor=accuracy_op)

merged_summary = tf.summary.merge_all()

# Step 5: Run Graph
with tf.Session() as sess:
    # debug writer
    log_name = "logs/{}".format(time.time())
    train_writer = tf.summary.FileWriter(logdir=log_name + '_train/',
                                         graph=sess.graph)

    validation_writer = tf.summary.FileWriter(logdir=log_name + '_val/')

    sess.run(tf.global_variables_initializer())
    sess.run(input_iter.initializer, feed_dict={data_x: train.data, data_y: train.fine_labels})

    global_batch_count = 0
    half_epoch_count = 0
    while True:
        try:
            global_batch_count += 1

            if global_batch_count % HALF_EPOCH_SIZE == 0:
                half_epoch_count += 1
                print('Ran half epoch ' + str(half_epoch_count))

                _, loss, accuracy, batch_summary = sess.run([train_step, loss_op, accuracy_op, merged_summary])
                validation_writer.add_summary(batch_summary,
                                              global_step=global_batch_count)
            else:
                _, loss, accuracy, batch_summary = sess.run([train_step, loss_op, accuracy_op, merged_summary])
                train_writer.add_summary(batch_summary,
                                         global_step=global_batch_count)

        except tf.errors.OutOfRangeError:
            print('End of Epochs')
            break

