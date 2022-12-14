# -*- coding: utf-8 -*-
"""
NMT.py
Neural Machine Translation (NMT) using Recurrent Neural Network (RNN)
"""
import argparse

import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
import numpy as np
import sys
import os
# From keras import
from tensorflow.python.keras.models import Model
from tensorflow.python.keras.layers import Input, Dense, GRU, Embedding
# from tensorflow.python.keras.optimizers import RMSprop
from tensorflow.python.keras.optimizers import rmsprop_v2
from tensorflow.python.keras.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard
from tensorflow.python.keras.preprocessing.text import Tokenizer
from tensorflow.python.keras.preprocessing.sequence import pad_sequences

from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction


# load data
file1 = open("./data/train.en", encoding="utf8")  # English Data
english = file1.readlines()

file2 = open("./data/train.vi", encoding="utf8")  # Vietnamese Data
vitn = file2.readlines()

# add a start and end marker for the destination language.
for i in range(0, len(vitn)):
    vitn[i] = "starttt " + vitn[i] + " enddd"

# Most frequent 10,000 words for tokenizing.
num_words = 10000


# Tokenizer Wrapper class
class TokenizerWrap(Tokenizer):
    
    def __init__(self, texts, padding,
                 reverse=False, num_words=None):

        Tokenizer.__init__(self, num_words=num_words)
        self.fit_on_texts(texts)

        # Create inverse lookup from integer-tokens to words.
        self.index_to_word = dict(zip(self.word_index.values(),
                                      self.word_index.keys()))
        self.tokens = self.texts_to_sequences(texts)

        if reverse:

            self.tokens = [list(reversed(x)) for x in self.tokens]
            truncating = 'pre'
        else:

            truncating = 'post'

        self.num_tokens = [len(x) for x in self.tokens]

        self.max_tokens = np.mean(self.num_tokens) \
                          + 2 * np.std(self.num_tokens)
        self.max_tokens = int(self.max_tokens)
        self.tokens_padded = pad_sequences(self.tokens,
                                           maxlen=self.max_tokens,
                                           padding=padding,
                                           truncating=truncating)

    def token_to_word(self, token):

        word = " " if token == 0 else self.index_to_word[token]
        return word

    def tokens_to_string(self, tokens):
        words = [self.index_to_word[token]
                 for token in tokens
                 if token != 0]

        text = " ".join(words)

        return text

    def text_to_tokens(self, text, reverse=False, padding=False):

        tokens = self.texts_to_sequences([text])
        tokens = np.array(tokens)

        if reverse:
            tokens = np.flip(tokens, axis=1)

            truncating = 'pre'
        else:

            truncating = 'post'

        if padding:
            tokens = pad_sequences(tokens,
                                   maxlen=self.max_tokens,
                                   padding='pre',
                                   truncating=truncating)
        return tokens
# tokenize the datasets

tokenizer_eng = TokenizerWrap(texts=english,
                              padding='pre',
                              reverse=True,
                              num_words=num_words)

tokenizer_vitn = TokenizerWrap(texts=vitn,
                               padding='post',
                               reverse=False,
                               num_words=num_words)

# reduce the memory
tokens_eng = tokenizer_eng.tokens_padded
tokens_vitn = tokenizer_vitn.tokens_padded

encoder_input_data = tokens_eng

decoder_input_data = tokens_vitn[:, :-1]  # They are in reverse format, so reverse them
decoder_output_data = tokens_vitn[:, 1:]  # First 'start' marker is time stepped in output

#######################################################################
# Neural Network
#######################################################################

#######################################################################
# Encoder
#######################################################################
encoder_input = Input(shape=(None,), name='encoder_input')

embedding_size = 128
state_size = 512

encoder_embedding = Embedding(input_dim=num_words,
                              output_dim=embedding_size,
                              name='encoder_embedding')

encoder_gru1 = GRU(state_size, name='encoder_gru1',
                   return_sequences=True)
encoder_gru2 = GRU(state_size, name='encoder_gru2',
                   return_sequences=True)
encoder_gru3 = GRU(state_size, name='encoder_gru3',
                   return_sequences=False)


def connect_encoder():
    # Start the neural network with its input-layer.
    net = encoder_input

    # Connect the embedding-layer.
    net = encoder_embedding(net)

    # Connect all the GRU-layers.
    net = encoder_gru1(net)
    net = encoder_gru2(net)
    net = encoder_gru3(net)

    # This is the output of the encoder.
    encoder_output = net

    return encoder_output


encoder_output = connect_encoder()

#######################################################################
# Decoder
#######################################################################
decoder_initial_state = Input(shape=(state_size,),
                              name='decoder_initial_state')

decoder_input = Input(shape=(None,), name='decoder_input')
decoder_embedding = Embedding(input_dim=num_words,
                              output_dim=embedding_size,
                              name='decoder_embedding')

decoder_gru1 = GRU(state_size, name='decoder_gru1',
                   return_sequences=True)
decoder_gru2 = GRU(state_size, name='decoder_gru2',
                   return_sequences=True)
decoder_gru3 = GRU(state_size, name='decoder_gru3',
                   return_sequences=True)

decoder_dense = Dense(num_words, activation='linear', name='decoder_output')


def connect_decoder(initial_state):
    # Start the decoder-network with its input-layer.
    net = decoder_input

    # Connect the embedding-layer.
    net = decoder_embedding(net)

    # Connect all the GRU-layers.
    net = decoder_gru1(net, initial_state=initial_state)
    net = decoder_gru2(net, initial_state=initial_state)
    net = decoder_gru3(net, initial_state=initial_state)

    # Connect the final dense layer that converts to one-hot encoded arrays.
    decoder_output = decoder_dense(net)

    return decoder_output


#######################################################################
# connecting all layers and creating the model.
#######################################################################

decoder_output = connect_decoder(initial_state=encoder_output)

model_train = Model(inputs=[encoder_input, decoder_input], outputs=[decoder_output])

model_encoder = Model(inputs=[encoder_input],
                      outputs=[encoder_output])

decoder_output = connect_decoder(initial_state=decoder_initial_state)

model_decoder = Model(inputs=[decoder_input, decoder_initial_state],
                      outputs=[decoder_output])


def sparse_cross_entropy(y_true, y_pred):
    """
    Calculate the cross-entropy loss between y_true and y_pred.
    """
    # 2-rank tensor of shape [batch_size, sequence_length]
    loss = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=y_true,
                                                          logits=y_pred)

    loss_mean = tf.reduce_mean(loss)

    return loss_mean


#######################################################################
# Compile the model.
#######################################################################

optimizer = rmsprop_v2.RMSprop(lr=1e-3)
decoder_target = tf.placeholder(dtype='int32', shape=(None, None))
model_train.compile(optimizer=optimizer,
                    loss=sparse_cross_entropy,
                    target_tensors=[decoder_target])

def load_trained_model():
    PRETRAINED_MODEL_PATH = './model/training_model.h5'
    if os.path.exists(PRETRAINED_MODEL_PATH):
        model_train = tf.keras.models.load_model(PRETRAINED_MODEL_PATH, compile=False, custom_objects={'sparse_cross_entropy': sparse_cross_entropy})


# Callbacks
path_checkpoint = 'checkpoint.keras'
callback_checkpoint = ModelCheckpoint(filepath=path_checkpoint,
                                      monitor='val_loss',
                                      verbose=1,
                                      save_weights_only=True,
                                      save_best_only=True)
callback_early_stopping = EarlyStopping(monitor='val_loss',
                                        patience=3, verbose=1)
callbacks = [callback_early_stopping,
             callback_checkpoint,
            ]


x_data = {
    'encoder_input': encoder_input_data,
    'decoder_input': decoder_input_data
}

y_data = {
    'decoder_output': decoder_output_data
}

MODEL_PATH = './model/'


#######################################################################
# train and save the trained model.
#######################################################################

def train():
    print("Training in progress ...")
    validation_split = 10000 / len(encoder_input_data)
    print(validation_split)
#     model_train.compile(optimizer=optimizer,
#                     loss=sparse_cross_entropy,
#                     target_tensors=[decoder_target])
    model_train.fit(x=x_data,
                    y=y_data,
                    batch_size=512,
                    epochs=10,
                    validation_split=validation_split,
                    callbacks=callbacks)
    model_train.save(MODEL_PATH + 'training_model.h5')


mark_start = 'starttt'
mark_end = 'enddd'
token_start = tokenizer_vitn.word_index[mark_start.strip()]
token_end = tokenizer_vitn.word_index[mark_end.strip()]


#######################################################################
# Function to translate the string input.
#######################################################################
def translate(input_text, true_output_text=None):
    """Translate a single text-string."""
    input_tokens = tokenizer_eng.text_to_tokens(text=input_text,
                                                reverse=True,
                                                padding=True)

    # Get the output of the encoder's GRU which will be
    # used as the initial state in the decoder's GRU.
    initial_state = model_encoder.predict(input_tokens)

    # Max number of tokens / words in the output sequence.
    max_tokens = tokenizer_vitn.max_tokens

    # Pre-allocate the 2-dim array used as input to the decoder.
    # This holds just a single sequence of integer-tokens,
    # but the decoder-model expects a batch of sequences.
    shape = (1, max_tokens)
    decoder_input_data = np.zeros(shape=shape, dtype=np.int)

    # The first input-token is the special start-token for 'ssss '.
    token_int = token_start

    # Initialize an empty output-text.
    output_text = ''

    # Initialize the number of tokens we have processed.
    count_tokens = 0

    # While we haven't sampled the special end-token for ' eeee'
    # and we haven't processed the max number of tokens.
    while token_int != token_end and count_tokens < max_tokens:
        # Update the input-sequence to the decoder
        # with the last token that was sampled.
        # In the first iteration this will set the
        # first element to the start-token.
        decoder_input_data[0, count_tokens] = token_int

        # Wrap the input-data in a dict for clarity and safety,
        # so we are sure we input the data in the right order.
        x_data = \
            {
                'decoder_initial_state': initial_state,
                'decoder_input': decoder_input_data
            }

        # Input this data to the decoder and get the predicted output.
        decoder_output = model_decoder.predict(x_data)

        # Get the last predicted token as a one-hot encoded array.
        token_onehot = decoder_output[0, count_tokens, :]

        # Convert to an integer-token.
        token_int = np.argmax(token_onehot)

        # Lookup the word corresponding to this integer-token.
        sampled_word = tokenizer_vitn.token_to_word(token_int)

        # Append the word to the output-text.
        output_text += " " + sampled_word

        # Increment the token-counter.
        count_tokens += 1

    output_text = output_text.rsplit(' ', 1)[0]

    # Sequence of tokens output by the decoder.
    output_tokens = decoder_input_data[0]
    # Print the input-text.
    print("Input text is:")
    print(input_text)
    print()

    # Print the translated output-text.
    print("Translated text is:")
    print(output_text)
    print()

    # Optionally print the true translated text.
    if true_output_text is not None:
        print("True output text is:")
        print(true_output_text)
        print()

    return input_text, output_text, true_output_text



def translate1(input_text, true_output_text=None):
    """Translate a single text-string."""
    input_tokens = tokenizer_eng.text_to_tokens(text=input_text,
                                                reverse=True,
                                                padding=True)

    # Get the output of the encoder's GRU which will be
    # used as the initial state in the decoder's GRU.
    initial_state = model_encoder.predict(input_tokens)

    # Max number of tokens / words in the output sequence.
    max_tokens = tokenizer_vitn.max_tokens

    # Pre-allocate the 2-dim array used as input to the decoder.
    # but the decoder-model expects a batch of sequences.
    shape = (1, max_tokens)
    decoder_input_data = np.zeros(shape=shape, dtype=np.int)

    # The first input-token is the special start-token for 'ssss '.
    token_int = token_start

    # Initialize an empty output-text.
    output_text = ''

    # Initialize the number of tokens we have processed.
    count_tokens = 0

    # While we haven't sampled the special end-token for ' eeee'
    # and we haven't processed the max number of tokens.
    while token_int != token_end and count_tokens < max_tokens:
        # Update the input-sequence to the decoder
        # with the last token that was sampled.
        # In the first iteration this will set the
        # first element to the start-token.
        decoder_input_data[0, count_tokens] = token_int

        # Wrap the input-data in a dict for clarity and safety,
        # so we are sure we input the data in the right order.
        x_data = \
            {
                'decoder_initial_state': initial_state,
                'decoder_input': decoder_input_data
            }

        y_data = \
            {
                'encoder_input': input_tokens,
                'decoder_input': decoder_input_data
            }


        # Input this data to the decoder and get the predicted output.
        #decoder_output = model_decoder.predict(x_data)
        decoder_output = model_train.predict(y_data)

        # Get the last predicted token as a one-hot encoded array.
        token_onehot = decoder_output[0, count_tokens, :]

        # Convert to an integer-token.
        token_int = np.argmax(token_onehot)

        # Lookup the word corresponding to this integer-token.
        sampled_word = tokenizer_vitn.token_to_word(token_int)

        # Append the word to the output-text.
        output_text += " " + sampled_word

        # Increment the token-counter.
        count_tokens += 1

    output_text = output_text.rsplit(' ', 1)[0].strip()
    #output_text = output_text.rsplit(' ', 1)[0]
    # Sequence of tokens output by the decoder.
    output_tokens = decoder_input_data[0]
    # Print the input-text

    return input_text, output_text, true_output_text


#######################################################################
# test the model and BLEU score.
#######################################################################


sm = SmoothingFunction()


def test():
    load_trained_model
    # Load the data
    file1 = open("./data/tst2013.en", encoding="utf8")  # Load English Data
    english_test = file1.readlines()

    file2 = open("./data/tst2013.vi", encoding="utf8")  # Load Vietnamese Data
    vitn_test = file2.readlines()

    # adding start and end marker for the destination language.
    for i in range(0, len(vitn_test)):
        vitn_test[i] = "starttt " + vitn_test[i] + " enddd"

    # count = 0
    scores_list = []
    print('Test : ')
    for idx in range(0, 20):  # Doing for 20 lines
        input_text, output_text, true_output_text = translate1(input_text=english_test[idx],
                                                               true_output_text=vitn_test[idx])
        true_output_text = true_output_text.partition(' ')[2].rsplit('\n', 1)[0].replace(" .", "").lower()
        #print(true_output_text)

        scor = sentence_bleu([output_text], true_output_text, smoothing_function=sm.method1)
        scores_list.append(scor)
        print(output_text)


    BLEU_average = sum(scores_list) / 20
    print("The BLEU average score on the test_data = ", BLEU_average)
    print('BLEU score in % = ', BLEU_average * 100)
    # print(count)

    return BLEU_average


def _get_user_input():
    """ Get user's input, which will be transformed into encoder input later """
    print("> ", end="")
    sys.stdout.flush()
    return sys.stdin.readline()

def main():

    parser = argparse.ArgumentParser(description='NMT')
    parser.add_argument('function', nargs=1, type=str, choices={'train', 'test', 'translate'}, )

    args = parser.parse_args()

    if args.function[0] == 'train':
        print("Training Model")
        train()
    elif args.function[0] == 'test':
        print("Loading Model to Test...")
        test()
    elif args.function[0] == 'translate':
        print("Loading Model to translate")
        load_trained_model
        while True:
            line = _get_user_input()
            if len(line) > 0 and line[-1] == '\n':
                line = line[:-1]
            if line == '':
                break

            input_text, output_text, true_output_text = translate1(input_text=line)
            print('Input : ' + input_text + '\n')
            print('Output : ' + output_text + '\n')
        print('=============================================\n')
    else:
        print('\nPlease enter a valid command')
        parser.print_help()

    exit()

if __name__ == '__main__' : 
    main()
