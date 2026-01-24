class Budget:
    # all = 使えるお金を割合で分配
    def __init__(self):
        self.budget = [0,40, 58, 2] # [all, pension, industry, military] all以外は割合%表示
        self.past_budget = []
        pass
    
    def change_budget(self,all, pension, industry, military):
        self.past_budget.append(self.budget)
        self.budget = [all,pension, industry, military]
    
    def set_budget(self, all,pension, industry, military):
        self.budget = [all,pension, industry, military]
        
    def get_past_budget(self, turn_year=0):
        return self.past_budget[len(self.past_budget) - 1 - turn_year]
    
    
    
    