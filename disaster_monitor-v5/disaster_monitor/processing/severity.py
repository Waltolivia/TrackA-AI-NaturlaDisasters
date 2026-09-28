RANK={'Unknown':0,'Minor':1,'Moderate':2,'Severe':3,'Extreme':4}
def escalated(old,new): return RANK.get(new,0)>RANK.get(old,0)
