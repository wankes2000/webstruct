# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import unittest
import pickle
import tempfile

import webstruct
from webstruct.features import EXAMPLE_TOKEN_FEATURES
from webstruct.crfsuite import create_crfsuite_pipeline
from webstruct.metrics import bio_classification_report
from webstruct.model import NER
from webstruct.utils import train_test_split_noshuffle
from .utils import get_trees, DATA_PATH


class CRFsuiteTest(unittest.TestCase):

    TAGSET = ['ORG', 'CITY', 'STREET', 'ZIPCODE', 'STATE', 'TEL', 'FAX']

    def _get_Xy(self, num):
        trees = get_trees(num)
        html_tokenizer = webstruct.HtmlTokenizer(tagset=self.TAGSET)
        return html_tokenizer.tokenize(trees)

    def _get_train_test(self, train_size, test_size):
        X, y = self._get_Xy(train_size+test_size)
        return train_test_split_noshuffle(X, y, test_size=test_size)

    def get_pipeline(self, **kwargs):
        params = dict(
            token_features=EXAMPLE_TOKEN_FEATURES,
            train_params={
                'max_iterations': 30,
                'c1': 1,
                'c2': 0.01,
            }
        )
        params.update(kwargs)
        return create_crfsuite_pipeline(**params)

    def test_training_tagging(self):
        X_train, X_test, y_train, y_test = self._get_train_test(8, 2)

        # Train the model:
        model = self.get_pipeline()
        model.fit(X_train, y_train)

        # Model should learn something:

        # y_pred = model.predict(X_test)
        # print(bio_classification_report(y_test, y_pred))
        assert model.score(X_test, y_test) > 0.3

        # It should handle files automatically:
        crf = model.steps[-1][1]
        filename = crf.model_filename_
        self.assertTrue(os.path.isfile(filename))

        # Temporary files should be collected.
        # XXX: does it work in pypy, and should we care?
        del crf
        del model
        self.assertFalse(os.path.isfile(filename))

    def test_pickle(self):
        X_train, X_test, y_train, y_test = self._get_train_test(8, 2)

        model = self.get_pipeline()
        model.fit(X_train, y_train)
        score = model.score(X_test, y_test)
        assert score > 0.3

        data = pickle.dumps(model, pickle.HIGHEST_PROTOCOL)
        filename = model.steps[-1][1].model_filename_

        # make sure model file is gone
        del model
        try:
            os.unlink(filename)
        except OSError:
            pass

        # model should work after unpickling
        model2 = pickle.loads(data)
        score2 = model2.score(X_test, y_test)
        assert score2 > 0.3
        assert abs(score2-score) < 1e-6

    def test_explicit_modelname(self):
        X_train, X_test, y_train, y_test = self._get_train_test(8, 2)

        # pass a custom model_filename to the constructor
        _, fname = tempfile.mkstemp('.crfsuite', 'tst-model-')
        model = self.get_pipeline(model_filename=fname)
        model.fit(X_train, y_train)

        crf = model.steps[-1][1]
        self.assertFalse(crf._modelfile_auto)
        self.assertEqual(crf.model_filename_, fname)

        # the file should be preserved when the model is closed
        del crf
        del model
        self.assertTrue(os.path.isfile(fname))

        # we shouldn't need to train the model again
        model2 = self.get_pipeline(model_filename=fname)
        assert model2.score(X_test, y_test) > 0.3

        # and it should work after pickling/unpickling
        dump = pickle.dumps(model2, pickle.HIGHEST_PROTOCOL)

        assert model2.score(X_test, y_test) > 0.3
        self.assertTrue(os.path.isfile(fname))

        model3 = pickle.loads(dump)
        assert model3.score(X_test, y_test) > 0.3
        self.assertTrue(os.path.isfile(fname))
        self.assertEqual(model3.steps[-1][1].model_filename_, fname)

        # cleanup
        os.unlink(fname)

    def test_ner(self):
        X, y = self._get_Xy(10)
        model = self.get_pipeline()
        model.fit(X, y)

        ner = NER(model)

        # Load 7.html file - model is trained on it, so
        # the prediction should work well.
        with open(os.path.join(DATA_PATH, '7.html'), 'rb') as f:
            html = f.read()

        groups = ner.extract_groups(html, dont_penalize={'TEL', 'FAX'})
        group1 = [
            (u'4503 W. Lovers Lane', 'STREET'),
            (u'Dallas', 'CITY'),
            (u'TX', 'STATE'),
            (u'75206', 'ZIPCODE'),
            (u'214-351-2456', 'TEL'),
            (u'214-904-1716', 'FAX'),
        ]
        group2 = [
            (u'4515 W. Lovers Lane', 'STREET'),
            (u'Dallas', 'CITY'),
            (u'TX', 'STATE'),
            (u'75206', 'ZIPCODE'),
            (u'214-352-0031', 'TEL'),
            (u'214-350-5302', 'TEL'),
        ]
        self.assertIn(group1, groups)
        self.assertIn(group2, groups)

        # pickle/unpickle NER instance
        dump = pickle.dumps(ner, pickle.HIGHEST_PROTOCOL)
        ner2 = pickle.loads(dump)

        self.assertNotEqual(
            ner.model.steps[-1][1].model_filename_,
            ner2.model.steps[-1][1].model_filename_,
        )

        groups = ner2.extract_groups(html, dont_penalize={'TEL', 'FAX'})
        self.assertIn(group1, groups)
        self.assertIn(group2, groups)