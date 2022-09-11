def insert(stack,p):
    stack.append(p)
    l=len(stack)-1
    print("\n",p,"IS ADDED SUCCESSFULLY\n")
def display(stack):
    l=len(stack)
    if l==0:
        print(".....UNDERFLOW.....")
    else: 
        print("ELMENTS PRESENT IN STACKS ARE:")
        for i in range(0,len(stack)):
            print(stack[i])
def delete(stack):
    l=len(stack)
    if len(stack)==0:
        print(".....UNDERFLOW.....")
    else:
        d=stack.pop()
        l=len(stack)-1
        print("\n",d,"ELEMENT DELETED SUCCESSFULLY\n")
def search(stack,t):
    if len(stack)==0:
            print(".....UNDERFLOW.....")
    else:
        for i in range(0,len(stack)):
            if t==stack[i]:
                print("\n",t,"IS PRESENT IN THE STACK.")
            elif t!=stack[i]:
                print("ELEMENT NOT FOUND")
def peek(stack):
    if len(stack)==0:
        print(".....UNDERFLOW.....")
    else:
        print("TOP->",stack[len(stack)-1])
stack=[]
l=None
print("-------------MENU DRIVEN PROGRAM---------------")
while True:
    print("Stack Operations\n1.PUSH\n2.DISPLAY\n3.POP\n4.SEARCH\n5.PEEK\n6.EXIT\n")
    chance=int(input("Enter which operation you would like to perform:"))
    if chance==1:
        n=int(input("Enter no. of elements to be ADDED:"))
        for i in range(0,n):
            p=int(input("Enter a number to INPUTTED:"))
            insert(stack,p)
    elif chance==2:
        display(stack)
    elif chance==3:
        delete(stack)
    elif chance==4:
        t=int(input("Enter element to SEARCHED:"))
        search(stack,t)
    elif chance==5:
        peek(stack)
    elif chance==6:
        break
    else:
        print("you have entered WRONG INPUT.Try again.....")
