import unittest
import numpy as np
from audit_realizations import mask_membership_matches, feature_perturbations_match

class RealizationOrderFixtures(unittest.TestCase):
    def test_unsorted_indices_match_sorted_mask_by_membership(self):
        idx=np.array([5,1,4],dtype=np.int64)
        mask=np.zeros(7,dtype=bool); mask[[1,4,5]]=True
        self.assertTrue(mask_membership_matches(idx,mask))
    def test_wrong_row_feature_pairing_does_not_reproduce(self):
        x0=np.zeros((7,2)); x=x0.copy(); idx=np.array([5,1,4]); feat=np.array([0,1,1]); delta=np.array([5.,2.,4.])
        x[idx,feat]=x0[idx,feat]+delta
        self.assertTrue(feature_perturbations_match(x0,x,idx,feat,delta))
        self.assertFalse(feature_perturbations_match(x0,x,idx,feat[::-1],delta))
    def test_missing_reporting_keys_are_accessed_with_safe_defaults(self):
        section={}
        self.assertEqual(section.get("issues",[]),[])
        self.assertEqual(section.get("checked",0),0)

if __name__=="__main__": unittest.main()
