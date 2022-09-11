'''
    the trick for binary search(x=45) is shown below
            l=1  |1|2|3|45|100| h=100,m=3
                    since 45>3
                so l=3 h=100 and m=45
                  at x=m return True
'''

def BinarySearch(a,l,r,s):
    m = 1+ (r-1)//2
    if r>=1:
        if a[m]==s:
            return m
        elif a[m]>s:
            BinarySearch(a,m+1,-1,s)
        else:
            BinarySearch(a,0,m-1,s)
    else:
        return -1

n=int(input("Enter the number of elements:"))
a=[]
for i in range(0,n):
    x=int(input("Enter element:"))
    a.append(x)

s=int(input("Enter the element to be searched:"))
result=BinarySearch(a,0,len(a)-1,s)
if (result == -1):
    print("Not Found!!")
else:
    print("Element is present at ",i)
