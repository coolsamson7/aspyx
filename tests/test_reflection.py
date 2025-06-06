from __future__ import annotations

import inspect
from inspect import signature, getmembers
from typing import Callable, get_type_hints, Type, Dict


import logging
import unittest

class TestReflection(unittest.TestCase):
    def test_1(self):
       pass
        #self.assertEqual(answer, "hello")

def suite():
    suite = unittest.TestSuite()

    suite.addTest(unittest.makeSuite(TestReflection))

    return suite


if __name__ == '__main__':
    #unittest.main()
    runner = unittest.TextTestRunner()
    runner.run(suite())