class Interest:
    def __init__(self, initial_interest):
        self.interest = [initial_interest]
    
    def change_interest(self, ninterest):
        self.interest.append(ninterest)
        
    
    def get_true_interest(self):
        assert len(self.interest) > 0, "Interest list is empty."
        true_interest = 0.0
        weight_sum = 0.0
        for i in range(len(self.interest)):
            weight = 1.0 + i / len(self.interest)
            weight *= weight
            true_interest += self.interest[i] * weight
            weight_sum += weight
        return true_interest / weight_sum if weight_sum != 0 else 0.0
    
    def get_interest(self):
        assert len(self.interest) > 0, "Interest list is empty."
        return self.interest[-1]