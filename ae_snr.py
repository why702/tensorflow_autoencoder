#!/usr/bin/env python""" autoencoder for fingerprint"""import timeimport osimport sys# import matplotlib.pyplot as plt# from PIL import Imageimport numpy as npimport cv2import mathimport data_augmentationimport tensorflow as tffrom tensorflow.contrib.layers import conv2d, conv2d_transpose, l2_regularizerfrom tensorflow.contrib.framework import arg_scope# from SSIM_PIL import compare_ssim as ssimfrom tensorflow.contrib.slim import get_variables_to_restoreimport util__author__ = "Bill Wang"__copyright__ = ""__credits__ = []__license__ = ""__version__ = "1.0.0.2"__maintainer__ = "Bill Wang"__email__ = "why702@gmail.com"__status__ = "Study"def autoencoder(input, d, weights_regularizer=0.0005):    with arg_scope([conv2d, conv2d_transpose],                   padding='SAME',                   activation_fn=tf.nn.leaky_relu,                   weights_regularizer=l2_regularizer(weights_regularizer)):        # Encode-----------------------------------------------------------        net = conv2d(input, 32, [4, 4], stride=2)        net = conv2d(net, 32, [4, 4], stride=2)        net = conv2d(net, 32, [3, 3], stride=1)        net = conv2d(net, 64, [4, 4], stride=2)        net = conv2d(net, 64, [3, 3], stride=1)        encoded = conv2d(net, d, [8, 8], stride=1)        # Decode---------------------------------------------------------------------        # net = conv2d_transpose(encoded, 32, [8, 8], stride=1)        net = conv2d(encoded, d, [8, 8], stride=1)        net = conv2d(net, 64, [3, 3], stride=1)        # net = conv2d_transpose(net, 32, [4, 4], stride=2)        net = tf.image.resize_nearest_neighbor(            net, (2 * net.get_shape()[1], 2 * net.get_shape()[2]))        net = conv2d(net, 32, [4, 4], stride=1)        net = conv2d(net, 32, [3, 3], stride=1)        # net = conv2d_transpose(net, 32, [4, 4], stride=2)        net = tf.image.resize_nearest_neighbor(            net, (2 * net.get_shape()[1], 2 * net.get_shape()[2]))        net = conv2d(net, 32, [4, 4], stride=1)        # decoded = conv2d_transpose(net, 1, [4, 4], stride=2)        net = tf.image.resize_nearest_neighbor(            net, (2 * net.get_shape()[1], 2 * net.get_shape()[2]))        decoded = conv2d(net, 1, [4, 4], stride=1)    return decodeddef train_opt(total_loss, global_step, optimizer, learning_rate,              moving_average_decay, update_gradient_vars):    if optimizer == 'ADAGRAD':        opt = tf.train.AdagradOptimizer(learning_rate)    elif optimizer == 'ADADELTA':        opt = tf.train.AdadeltaOptimizer(learning_rate, rho=0.9, epsilon=1e-6)    elif optimizer == 'ADAM':        opt = tf.compat.v1.train.AdamOptimizer(learning_rate,                                     beta1=0.9,                                     beta2=0.999,                                     epsilon=0.1)    elif optimizer == 'RMSPROP':        opt = tf.train.RMSPropOptimizer(learning_rate,                                        decay=0.9,                                        momentum=0.9,                                        epsilon=1.0)    elif optimizer == 'MOM':        opt = tf.train.MomentumOptimizer(learning_rate, 0.9, use_nesterov=True)    else:        raise ValueError('Invalid optimization algorithm')    grads = opt.compute_gradients(total_loss, update_gradient_vars)    # Apply gradients.    apply_gradient_op = opt.apply_gradients(grads, global_step=global_step)    # Track the moving averages of all trainable variables.    variable_averages = tf.train.ExponentialMovingAverage(        moving_average_decay, global_step)    variables_averages_op = variable_averages.apply(tf.trainable_variables())    with tf.control_dependencies([apply_gradient_op, variables_averages_op]):        train_op = tf.no_op(name='train')    return train_opdef save_variables_and_metagraph(sess, saver, summary_writer, model_dir,                                 model_name, step):    # Save the model checkpoint    print('Saving variables')    start_time = time.time()    checkpoint_path = os.path.join(model_dir, 'model-%s.ckpt' % model_name)    saver.save(sess, checkpoint_path, global_step=step, write_meta_graph=False)    save_time_variables = time.time() - start_time    print('Variables saved in %.2f seconds' % save_time_variables)    metagraph_filename = os.path.join(model_dir, 'model-%s.meta' % model_name)    save_time_metagraph = 0    if not os.path.exists(metagraph_filename):        print('Saving metagraph')        start_time = time.time()        saver.export_meta_graph(metagraph_filename)        save_time_metagraph = time.time() - start_time        print('Metagraph saved in %.2f seconds' % save_time_metagraph)    summary = tf.Summary()    # pylint: disable=maybe-no-member    summary.value.add(tag='time/save_variables',                      simple_value=save_time_variables)    summary.value.add(tag='time/save_metagraph',                      simple_value=save_time_metagraph)    summary_writer.add_summary(summary, step)    print('save_variables_and_metagraph done')def train(sess, epoch, conf, index_dequeue_op, enqueue_op, epoch_size,          input_placeholder, control_placeholder, batch_size_placeholder, step,          loss, loss_list, train_op, summary_op, summary_writer, stat, random_rotate,          random_crop, random_flip, use_fixed_image_standardization):    batch_number = 0    # get shuffle 9000 index form the queue    index_epoch = sess.run(index_dequeue_op)    image_epoch = np.array(conf.train_list)[index_epoch]    # Enqueue one epoch of image paths and labels    image_array = np.expand_dims(np.array(image_epoch), axis=3)    control_value = conf.RANDOM_ROTATE * random_rotate + conf.RANDOM_CROP * random_crop + \        conf.RANDOM_FLIP * random_flip + conf.FIXED_STANDARDIZATION * use_fixed_image_standardization    control_array = np.ones(conf.batch_size * conf.epoch_size) * control_value    control_array = np.expand_dims(control_array, axis=1)    # enter queue with img_path, labels and control_value(for data    # augmentation)    sess.run(        enqueue_op, {            input_placeholder: image_array,            control_placeholder: control_array,            batch_size_placeholder: conf.batch_size        })    # Training loop    train_time = 0    while batch_number < epoch_size:        start_time = time.time()        feed_dict = {batch_size_placeholder: conf.batch_size}        tensor_list = [loss, loss_list[0], loss_list[1], loss_list[2], loss_list[3], train_op, step, learning_rate]        if batch_number % 100 == 0:            loss_, l2_loss, snr, l2_loss_BandpassFilter, img_gen_noise_std, _, step_, lr_, summary_str = sess.run(tensor_list +                                                         [summary_op],                                                         feed_dict=feed_dict)            summary_writer.add_summary(summary_str, global_step=step_)        else:            loss_, l2_loss, snr, l2_loss_BandpassFilter, img_gen_noise_std, _, step_, lr_ = sess.run(tensor_list, feed_dict=feed_dict)        stat['loss'][step_ - 1] = loss_        stat['learning_rate'][epoch - 1] = lr_        duration = time.time() - start_time        print('Epoch: [%d][%d/%d]\tTime %.3f\tLoss %2.3f\tLr %2.5f\tl2_loss %2.3f\tsnr %2.3f\tl2_loss_BandpassFilter %2.3f\timg_gen_noise_std %2.3f' %              (epoch, batch_number + 1, epoch_size, duration, loss_, lr_, l2_loss, snr, l2_loss_BandpassFilter, img_gen_noise_std))        batch_number += 1        train_time += duration    # Add validation loss and accuracy to summary    summary = tf.Summary()    # pylint: disable=maybe-no-member    summary.value.add(tag='time/total', simple_value=train_time)    summary_writer.add_summary(summary, global_step=step_)    return Truedef validate(sess, epoch, conf, enqueue_op, batch_size, input_placeholder,             control_placeholder, batch_size_placeholder, stat, loss, loss_list,             validate_every_n_epochs, use_fixed_image_standardization,             image_batch, decoded):    print('Running forward pass on validation set')    nrof_batches = max(len(conf.val_list) // batch_size,1)    nrof_images = max(nrof_batches * batch_size, 1)    # Enqueue one epoch of image paths and labels    image_array = np.expand_dims(np.array(conf.val_list[:nrof_images]), axis=3)    control_array = np.ones(        nrof_images    ) * conf.FIXED_STANDARDIZATION * use_fixed_image_standardization    control_array = np.expand_dims(control_array, axis=1)    sess.run(        enqueue_op, {            input_placeholder: image_array,            control_placeholder: control_array,            batch_size_placeholder: conf.batch_size        })    loss_array = np.zeros((nrof_batches, ), np.float32)    # Training loop    start_time = time.time()    input_imgs = None    for i in range(nrof_batches):        if i != nrof_batches - 1:            feed_dict = {batch_size_placeholder: conf.batch_size}            loss_, l2_loss, snr, l2_loss_BandpassFilter, img_gen_noise_std = sess.run([loss, loss_list[0], loss_list[1], loss_list[2], loss_list[3]], feed_dict=feed_dict)            loss_array[i] = loss_        else:            feed_dict = {batch_size_placeholder: conf.batch_size}            input_imgs, decoded_imgs, loss_, l2_loss, snr, l2_loss_BandpassFilter, img_gen_noise_std = sess.run(                [image_batch, decoded, loss, loss_list[0], loss_list[1], loss_list[2], loss_list[3]], feed_dict=feed_dict)            loss_array[i] = loss_        if i % 10 == 9:            print('.', end='')            sys.stdout.flush()    print('')    duration = time.time() - start_time    val_index = (epoch - 1) // validate_every_n_epochs    stat['val_loss'][val_index] = np.mean(loss_array)    print('Validation Epoch: %d\tTime %.3f\tLoss %2.3f\tl2_loss %2.3f\tsnr %2.3f\tl2_loss_BandpassFilter %2.3f\timg_gen_noise_std %2.3f' %          (epoch, duration, np.mean(loss_array), l2_loss, snr, l2_loss_BandpassFilter, img_gen_noise_std))    # feed_dict = {batch_size_placeholder: conf.batch_size}    # [decoded_imgs] = sess.run([decoded], feed_dict=feed_dict)    # show the result    if input_imgs is not None:        n = 6  # how many digits we will display        input_imgs_show = list(input_imgs[:n, :, :, 0])        for i in range(n):            input_imgs_show[i] = util.normalize_ndarray(input_imgs_show[i]) * 255            input_imgs_show[i] = input_imgs_show[i].astype(np.uint8)        concat_input = np.concatenate(input_imgs_show, axis=1)        decoded_imgs_show = list(decoded_imgs[:n, :, :, 0])        for i in range(n):            decoded_imgs_show[i] = util.normalize_ndarray(                decoded_imgs_show[i]) * 255            decoded_imgs_show[i] = decoded_imgs_show[i].astype(np.uint8)        concat_output = np.concatenate(decoded_imgs_show, axis=1)        # get fft        input_imgs_fft = list(input_imgs[:n, :, :, 0])        decoded_imgs_fft = list(decoded_imgs[:n, :, :, 0])        for i in range(n):            f = np.fft.fft2(input_imgs_fft[i])            dft = cv2.dft(np.float32(input_imgs_fft[i]), flags=cv2.DFT_COMPLEX_OUTPUT)            dft_shift = np.fft.fftshift(dft)            input_imgs_fft[i] = 20 * np.log(cv2.magnitude(dft_shift[:, :, 0], dft_shift[:, :, 1]))            # input_imgs_fft[i] = util.normalize_ndarray(input_imgs_fft[i]) * 255            input_imgs_fft[i] = input_imgs_fft[i].astype(np.uint8)            dft_ = cv2.dft(np.float32(decoded_imgs_fft[i]), flags=cv2.DFT_COMPLEX_OUTPUT)            dft_shift_ = np.fft.fftshift(dft_)            decoded_imgs_fft[i] = 20 * np.log(cv2.magnitude(dft_shift_[:, :, 0], dft_shift_[:, :, 1]))            # decoded_imgs_fft[i] = util.normalize_ndarray(decoded_imgs_fft[i]) * 255            decoded_imgs_fft[i] = decoded_imgs_fft[i].astype(np.uint8)            # cv2.imshow("0",input_imgs_fft[i])            # cv2.imshow("1",decoded_imgs_fft[i])            # cv2.waitKey()            # img = input_imgs[i, :, :, :]            # # _f_ = np.fft.fft2(img)            # # _fshift_ = np.fft.fftshift(_f_)            # # fft = 20 * np.log(np.abs(_fshift_))            #            # dft = cv2.dft(np.float32(img), flags=cv2.DFT_COMPLEX_OUTPUT)            # dft_shift = np.fft.fftshift(dft)            # fft = 20 * np.log(cv2.magnitude(dft_shift[:, :, 0], dft_shift[:, :, 1]))            #            # cv2.imshow("0",(util.normalize_ndarray(img) * 255).astype(np.uint8))            # cv2.imshow("1",(util.normalize_ndarray(fft) * 255).astype(np.uint8))            # cv2.waitKey()        concat_input_fft = np.concatenate(input_imgs_fft, axis=1)        concat_output_fft = np.concatenate(decoded_imgs_fft, axis=1)        concat = np.concatenate((concat_input, concat_input_fft, concat_output, concat_output_fft), axis=0)        cv2.imwrite("./debug" + str(epoch) + ".png", concat)def LPF_Butterworth(width, height, kRadius, kOrder):    fltDst = np.empty([height, width])    cx = width / 2    cy = height / 2    for row in range(height):        for col in range(width):            kDistance = math.sqrt((col - cx) ** 2 + (row - cy) ** 2)            fltDst[row][col] = 1 / (1 + pow((kDistance / kRadius),                                            (2 * kOrder)))    return fltDstdef HPF_Butterworth(width, height, kRadius, kOrder):    fltDst = np.empty([height, width])    cx = width / 2    cy = height / 2    for row in range(height):        for col in range(width):            kDistance = math.sqrt((col - cx) ** 2 + (row - cy) ** 2)            fltDst[row][col] = 1 - 1 / (1 + pow((kDistance / kRadius),                                                (2 * kOrder)))    return fltDstdef snr(img, width, height):    inch2mm = 25.4    m_nDPI = 508    szImage = (min(width, height) * inch2mm) / m_nDPI    fcUp = int(szImage / (0.15))  # newborns baby    fcLow = int(szImage / (0.5 * 2.0))  # grown-ups    fltNoiseLow = LPF_Butterworth(width, height, fcLow, 4)    fltNoiseHigh = HPF_Butterworth(width, height, fcUp, 4)    tf_fltNoiseLow = tf.convert_to_tensor(fltNoiseLow, dtype=tf.float32)    tf_fltNoiseLow_comx = tf.expand_dims(tf.complex(tf_fltNoiseLow, tf_fltNoiseLow),2)    tf_fltNoiseHigh = tf.convert_to_tensor(fltNoiseHigh, dtype=tf.float32)    tf_fltNoiseHigh_comx = tf.expand_dims(tf.complex(tf_fltNoiseHigh, tf_fltNoiseHigh),2)    # split signal / noise by fft    fft = tf.signal.fft2d(tf.cast(img, tf.complex64))    fft_low = tf.multiply(fft, tf_fltNoiseLow_comx)    fft_high = tf.multiply(fft, tf_fltNoiseHigh_comx)    img_low = tf.signal.ifft2d(fft_low)    img_high = tf.signal.ifft2d(fft_high)    img_signal = img - tf.math.real(img_low) - tf.math.real(img_high)    img_noise = img - img_signal    # crop    offset_height = int(height / 4)    offset_width = int(width / 4)    target_height = int(height / 2)    target_width = int(width / 2)    img_high = tf.image.crop_to_bounding_box(        img_high,        offset_height,        offset_width,        target_height,        target_width    )    img_signal = tf.image.crop_to_bounding_box(        img_signal,        offset_height,        offset_width,        target_height,        target_width    )    img_noise = tf.image.crop_to_bounding_box(        img_noise,        offset_height,        offset_width,        target_height,        target_width    )    #get SNR    img_signal_max = tf.math.reduce_max(img_signal, axis=(1,2,3))    img_signal_min = tf.math.reduce_min(img_signal, axis=(1,2,3))    img_noise_std = tf.math.reduce_std(img_noise, axis=(1,2,3))    img_high_noise_std = tf.math.reduce_std(tf.math.real(img_high), axis=(1,2,3))    img_signal_diff = img_signal_max - img_signal_min    snrSignalHigh = img_signal_diff / img_high_noise_std    snrSignalAll = img_signal_diff / img_noise_std    snrSignalHigh_mean = tf.math.reduce_mean(snrSignalHigh)    snrSignalAll_mean = tf.math.reduce_mean(snrSignalAll)    return snrSignalHigh_mean, snrSignalAll_meandef l2_loss(img_org, img_gen, width, height):    # crop    offset_height = int(height / 4)    offset_width = int(width / 4)    target_height = int(height / 2)    target_width = int(width / 2)    img_org = tf.image.crop_to_bounding_box(        img_org,        offset_height,        offset_width,        target_height,        target_width    )    img_gen = tf.image.crop_to_bounding_box(        img_gen,        offset_height,        offset_width,        target_height,        target_width    )    l2_loss = tf.reduce_mean(tf.reduce_sum(tf.pow(img_org - img_gen, 2), axis=(1, 2, 3)))    return l2_lossdef l2_loss_BandpassFilter(img_org, img_gen, width, height):    # inch2mm = 25.4    # m_nDPI = 508    # szImage = (min(width, height) * inch2mm) / m_nDPI    # fcUp = int(szImage / (0.15))  # newborns baby    # fcLow = int(szImage / (0.5 * 2.0))  # grown-ups    fcLow = 33    fcUp = 10    fltNoiseLow = LPF_Butterworth(width, height, fcLow, 4)    fltNoiseHigh = HPF_Butterworth(width, height, fcUp, 4)    tf_fltNoiseLow = tf.convert_to_tensor(fltNoiseLow, dtype=tf.float32)    tf_fltNoiseLow_comx = tf.expand_dims(tf.complex(tf_fltNoiseLow, tf_fltNoiseLow),2)    tf_fltNoiseHigh = tf.convert_to_tensor(fltNoiseHigh, dtype=tf.float32)    tf_fltNoiseHigh_comx = tf.expand_dims(tf.complex(tf_fltNoiseHigh, tf_fltNoiseHigh),2)    # split signal / noise by fft    fft_org = tf.signal.fft2d(tf.cast(img_org, tf.complex64))    fft_org_low = tf.multiply(fft_org, tf_fltNoiseLow_comx)    fft_org_high = tf.multiply(fft_org, tf_fltNoiseHigh_comx)    img_org_low = tf.signal.ifft2d(fft_org_low)    img_org_high = tf.signal.ifft2d(fft_org_high)    img_org_signal = img_org - tf.math.real(img_org_low) - tf.math.real(img_org_high)    fft_gen = tf.signal.fft2d(tf.cast(img_gen, tf.complex64))    fft_gen_low = tf.multiply(fft_gen, tf_fltNoiseLow_comx)    fft_gen_high = tf.multiply(fft_gen, tf_fltNoiseHigh_comx)    img_gen_low = tf.signal.ifft2d(fft_gen_low)    img_gen_high = tf.signal.ifft2d(fft_gen_high)    img_gen_signal = img_gen - tf.math.real(img_gen_low) - tf.math.real(img_gen_high)    img_gen_noise = img_gen - img_gen_signal    img_gen_noise_std = tf.reduce_mean(tf.math.reduce_std(img_gen_noise, axis=(1,2,3)))    # crop    offset_height = int(height / 4)    offset_width = int(width / 4)    target_height = int(height / 2)    target_width = int(width / 2)    img_org_signal = tf.image.crop_to_bounding_box(        img_org_signal,        offset_height,        offset_width,        target_height,        target_width    )    img_gen_signal = tf.image.crop_to_bounding_box(        img_gen_signal,        offset_height,        offset_width,        target_height,        target_width    )    l2_loss_BandpassFilter = tf.reduce_mean(tf.reduce_sum(tf.pow(img_org_signal - img_gen_signal, 2), axis=(1, 2, 3)))    return l2_loss_BandpassFilter, img_gen_noise_stdif __name__ == '__main__':    LOSS = 'l2_loss'    # LOSS = 'l2_loss_conv2d_transpose'    # LOSS = 'ssim'    model_dir = './model/{}'.format(LOSS)    if os.path.isdir(model_dir) == False:        os.makedirs(model_dir)    batch_size = 32    # epoch_size = 100    width = 136    height = 192    global_step = tf.Variable(name='global_step',                              initial_value=0,                              trainable=False)    input_placeholder = tf.compat.v1.placeholder(tf.float32,                                       shape=[None, height, width, 1],                                       name='input')    control_placeholder = tf.compat.v1.placeholder(tf.int32,                                         shape=(None, 1),                                         name='control')    batch_size_placeholder = tf.compat.v1.placeholder(tf.int32, name='batch_size')    conf = data_augmentation.configuration(        "D:/data/20191218_ET702_S10_16_v2.0.0.10_wash_20DB/NP_10/output_bin/image_raw/",        # "D:/data/20191218_ET702_S10_16_v2.0.0.10_wash_20DB/NP_10/output_bin/image_raw/P/13081202",        image_size=(height, width),        batch_size=batch_size)    image_batch, enqueue_op, index_dequeue_op = conf.run(        input_placeholder, control_placeholder, batch_size_placeholder)    image_batch = tf.identity(image_batch, 'image_batch')    image_batch = tf.identity(image_batch, 'input')    decoded = autoencoder(image_batch, 200)    snrSignalHigh_mean, snrSignalAll_mean = snr(decoded, width, height)    l2_loss = l2_loss(image_batch, decoded, width, height)    l2_loss_BandpassFilter, img_gen_noise_std = l2_loss_BandpassFilter(image_batch, decoded, width, height)    # if LOSS == 'ssim':    #     tf_ssim = tf.image.ssim(inputs, decoded, max_val=1.0)    #     loss = tf.reduce_mean(tf_ssim, name='reduce_mean')    # loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=inputs, logits=decoded))    # loss = tf.reduce_mean(tf.pow(decoded - image_batch, 2))    loss = l2_loss_BandpassFilter + img_gen_noise_std    loss_list = (l2_loss, snrSignalHigh_mean, l2_loss_BandpassFilter, img_gen_noise_std)    # Gather initial summaries.    summaries = set(tf.compat.v1.get_collection(tf.GraphKeys.SUMMARIES))    summaries.add(tf.compat.v1.summary.scalar('loss/%s' % loss.op.name, loss))    learning_rate = tf.compat.v1.train.piecewise_constant(        global_step,        boundaries=[40000, 60000, 80000, 1000000],  # lr_steps        values=[0.001, 0.0005, 0.0003, 0.0001, 0.00001],        # values=[0.00001, 0.00001, 0.00001, 0.00001],        name='lr_schedule')    # learning_rate = tf.train.exponential_decay(    #     learning_rate_placeholder,    #     global_step,    #     100 * 1000,    #     learning_rate_decay_factor,    #     staircase=True)    train_op = train_opt(loss, global_step, 'ADAM', learning_rate, 0.9999,                         tf.global_variables())    # Create a saver    saver = tf.compat.v1.train.Saver(tf.trainable_variables(), max_to_keep=3)    # Build the summary operation based on the TF collection of Summaries.    summary_op = tf.compat.v1.summary.merge(list(summaries), name='summary_op')    # Start running operations on the Graph.    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.8, allow_growth=True)    sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options,                                            log_device_placement=False))    sess.run(tf.global_variables_initializer())    sess.run(tf.local_variables_initializer())    summary_writer = tf.summary.FileWriter(os.path.join(model_dir, 'summary'),                                           sess.graph)    coord = tf.train.Coordinator()    tf.train.start_queue_runners(coord=coord, sess=sess)    pretrained_model = None    # pretrained_model = "D:/git/tensorflow_stacked_denoising_autoencoder_/model/model-ae.ckpt-290"    # ###    # if not pretrained_model:    #     checkpoint = 'D:/git/tensorflow_stacked_denoising_autoencoder_/model/l2_loss/model-ae.ckpt-290'    #     reader = tf.train.NewCheckpointReader(checkpoint)    #     var_to_shape_map = reader.get_variable_to_shape_map()    #    #     variables = get_variables_to_restore()    #     variables_to_restore = []    #     for v in variables:    #         if v.name[:-2] in list(var_to_shape_map.keys()):    #             if v.shape == var_to_shape_map[v.name[:-2]]:    #                 variables_to_restore.append(v)    #             else:    #                 print('{}: {} vs {}'.format(    #                     v.name[:-2], v.shape, var_to_shape_map[v.name[:-2]]))    #         else:    #             print('{} is not in ckpt.'.format(v.name[:-2]))    #    #     saver_bone = tf.compat.v1.train.Saver(variables_to_restore)    # ###    with sess.as_default():        if pretrained_model:            print('Restoring pretrained model: %s' % pretrained_model)            saver.restore(sess, pretrained_model)        # else:            # saver_bone.restore(sess, checkpoint)        # Training and validation loop        print('Running training')        max_nrof_epochs = 100000000        validate_every_n_epochs = 10        nrof_steps = max_nrof_epochs * conf.epoch_size        # Validate every validate_every_n_epochs as well as in the last        # epoch        nrof_val_samples = int(            math.ceil(max_nrof_epochs / validate_every_n_epochs))        stat = {            'loss': np.zeros((nrof_steps, ), np.float32),            'val_loss': np.zeros((nrof_val_samples, ), np.float32),            'learning_rate': np.zeros((max_nrof_epochs, ), np.float32),            'time_train': np.zeros((max_nrof_epochs, ), np.float32),            'time_validate': np.zeros((max_nrof_epochs, ), np.float32),        }        # pretrained_model = False        # pretrained_model = ""        if pretrained_model:            epoch_start = os.path.basename(pretrained_model).split(                sep='-')  # 20190227-143529/model-20190227-143529.ckpt-90            epoch_start = int(epoch_start[len(epoch_start) - 1])        else:            epoch_start = 1        # epoch_start = 1        for epoch in range(epoch_start, max_nrof_epochs + 1):            step = sess.run(global_step, feed_dict=None)            start_time = time.time()            cont = train(sess,                         epoch,                         conf,                         index_dequeue_op,                         enqueue_op,                         conf.epoch_size,                         input_placeholder,                         control_placeholder,                         batch_size_placeholder,                         global_step,                         loss,                         loss_list,                         train_op,                         summary_op,                         summary_writer,                         stat,                         random_rotate=1,                         random_crop=0,                         random_flip=1,                         use_fixed_image_standardization=0)            stat['time_train'][epoch - 1] = time.time() - start_time            if not cont:                break            start_time = time.time()            if len(conf.val_list) > 0 and (                    (epoch - 1) %                        validate_every_n_epochs == validate_every_n_epochs - 1                        or epoch == max_nrof_epochs):                validate(sess,                         epoch,                         conf,                         enqueue_op,                         batch_size,                         input_placeholder,                         control_placeholder,                         batch_size_placeholder,                         stat,                         loss,                         loss_list,                         validate_every_n_epochs,                         use_fixed_image_standardization=0,                         image_batch=image_batch,                         decoded=decoded)            stat['time_validate'][epoch - 1] = time.time() - start_time            # Save variables and the metagraph if it doesn't exist already            save_variables_and_metagraph(sess, saver, summary_writer,                                         model_dir, "ae", epoch)