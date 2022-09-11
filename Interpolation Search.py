def InterpolationSearch(a,l,h,s):
    pos=int(((x-a[l])*(h-l)/(a[h]-a[l]))+l)
    if (l<=h and x>a[l] and x<a[h]):
        if x==a[pos]:
            return pos
        if x>a[pos]:
            return InterpolationSearch(a,pos+1,h,s)
        if x<a[pos]:
            return InterpolationSearch(a,l,pos-1,s)
    
    return -1

n=int(input("Enter the number of elements:"))
a=[]
for i in range(0,n):
    x=int(input("Enter element:"))
    a.append(x)

s=int(input("Enter Element to be Searched:"))
result=InterpolationSearch(a,0,len(a)-1,s)
if result==-1:
    print("Not Found!!")
else:
    print("Element is present at ",result)
