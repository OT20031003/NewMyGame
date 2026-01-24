import math
class Satisfaction:
    # 満足度
    def __init__(self,initsatis  ,price, salary, tax, turn_year):
        
        self.satisfaction = initsatis
        self.befprice = price
        self.befsalary = salary
        self.beftax = tax
        self.turn_year = turn_year
    
    def save_list(self):
        return [self.satisfaction, self.befprice, self.befsalary, self.beftax, self.turn_year]
    
    def set_satisfaction(self, x):
        self.satisfaction = x
    
    def change_satisfaction(self, price, salary, tax, old):
        # 満足度を計算
        
        price_change = (price - self.befprice)/(self.befprice + 0.0001) - 0.05/self.turn_year
        salary_change = (salary - self.befsalary) / (self.befsalary + 0.00001)
        tax_change = (tax - self.beftax) / (self.beftax + 0.000001)
        price_change = math.tanh(price_change)*0.1
        salary_change = math.tanh(salary_change)*0.1
        tax_change = math.tanh(tax_change)*2
        a = 0.4 # 収入の影響
        b = -0.4 # 物価の影響
        c = -0.2 # 税金の影響
        if old == 20 or old == 21:
            a = 0.1
            b = -0.5
            c = -0.4
        satisfaction_change = a*salary_change + b*price_change  + c*tax_change
        #print(f"satis = {satisfaction_change}")
        self.satisfaction *= (1 + satisfaction_change) 
        #self.satisfaction -= int((old - (old % 10)) / 40)
        if self.satisfaction <= 20:
            self.satisfaction = 20
        if self.satisfaction > 100:
            self.satisfaction = 100.0
        return self.satisfaction
    
    def get_satisfaction(self):
        assert(self.satisfaction >= 0 and self.satisfaction <= 100), "Satisfaction value out of range: {}".format(self.satisfaction)
        return self.satisfaction
        
            
        