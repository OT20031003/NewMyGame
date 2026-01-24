import math
class Salary:
    def __init__(self, old, price, industry, init, coef):
        # 影響係数
        a = 100.0 # 産業の影響係数
        b = 100.0 # 物価の影響係数
        c = 300.0 # 年齢の影響係数
        
        # --- 変更点: 初期値計算用の固定基準値 ---
        # 実際の price や industry の値に関わらず、
        # 初期給与は「標準的な産業力(100)と物価(100)」を前提に計算します。
        # これにより、Salaryの初期値は coef (salary_p) だけでコントロール可能になります。
        base_industry = 100.0
        base_price = 100.0
        
        # 変動計算のために、現在の値を「前の値」として保持する
        self.befprice = price
        self.befindustry = industry
        
        # 初期給与の計算 (引数ではなく固定基準値を使用)
        self.salary = (a * base_industry + b * base_price + c * old) * coef
        
        if init >= 0:
            self.salary = init
        
        if old < 20 or old > 65:
            self.salary = 0.0
        self.befsalary = self.salary
    
    def save_list(self):
        return [self.befprice, self.befindustry, self.salary, self.befsalary]
        
    def set_salary(self, newsalary):
        self.befsalary = self.salary
        self.salary = newsalary
        
    def change_salary(self, industry, price, old):
        a = 2.0 # 産業の影響係数
        b = 1.5 # 物価の影響係数
        
        ho = self.salary
        # 変化率の計算 (現在の値 - 前の値) / 前の値
        ch_price = (price - self.befprice) / (self.befprice + 0.0001)
        ch_industry = (industry - self.befindustry) / (self.befindustry + 0.0001)
        
        #print(f"補正前 ch_price: {ch_price}, ch_industry: {ch_industry}")
        if self.befsalary == 0.0 and old != 20:
            self.salary = 0
            
        else:
            ch_price = math.tanh(ch_price) 
            ch_industry = math.tanh(ch_industry) * 0.15
            
            # 給与の更新
            self.salary = self.befsalary * (1 +  b * ch_price + a * ch_industry + 0.15/100)
            #print(f"Salary change: {self.salary} = {self.befsalary} * (1 + {b} * {ch_price} + {a} * {ch_industry} + 0.025)")
        
        if old < 20:
            self.salary = 0.0
        if old > 65:
            self.salary = ho
            
        # 値の更新
        self.befsalary = self.salary
        self.befprice = price
        self.befindustry = industry
    
    def get_salary(self):
        return self.salary
    
    def cut(self, val , limit):
        if val >= limit:
            val = limit
        if val <= -limit:
            val = -limit
        return val