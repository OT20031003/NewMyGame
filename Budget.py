class Budget:
    # all = 使えるお金を割合で分配
    def __init__(self):
        self.budget = [0, 40, 0, 20] # [all, pension, (legacy power=0), military] 未配分はReserves
        self.past_budget = []
        pass
    
    def change_budget(self, all, pension, power, military):
        self.past_budget.append(self.budget)
        self.budget = [all, pension, 0, military]
    
    def set_budget(self, all, pension, power, military):
        self.budget = [all, pension, 0, military]
        
    def get_past_budget(self, turn_year=0):
        return self.past_budget[len(self.past_budget) - 1 - turn_year]
    
    
    
    
