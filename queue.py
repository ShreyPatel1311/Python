def insert(queue,t):
    queue.append(t)
    if len(queue)==1:
        front=rear=0
    else:
        rear=len(queue)-1
def display(queue):
    if len(queue)==0:
        print(".....UNDERFLOW.....")
    else:
        print("FRONT- >",queue[0])
        for i in range(1,len(queue)-1):
            print("\t",queue[i])
        print("REAR - >",queue[-1])
def delete(queue):
    if len(queue)==0:
        print(".....UNDERFLOW.....")
    else:
        queue.pop(0)
        print("ELEMENT DELETED SUCCESSFULLY")
def search(queue,s):
    if len(queue)==0:
        print(".....UNDERFLOW.....")
    elif len(queue)!=0:
        if s in queue:
            print("ELEMENT FOUND.")
        else:
            print("ELEMENT NOT FOUND.")
def peek(queue):
    if len(queue)==0:
        print(".....UNDERFLOW.....")
    else:
        print("FRONT- >",queue[0])
        print("REAR - >",queue[len(queue)-1])
queue=[]
front=None
print("----------------MENU DRIVEN PROGRAM------------------")
print("Queue Operations")
while True:
    print("1.INSERT\n2.DISPLAY\n3.DELETE\n4.SEARCH\n5.PEEK\n6.EXIT")
    chance=int(input("Enter no.which you would like to perform:"))
    if chance==1:
        n=int(input("Enter no. of elements to be inputted:"))
        for i in range(0,n):
            t=int(input("Enter to be INPUTTED:"))
            insert(queue,t)
        print("ELEMENTS ADDED SUCCESSFULLY")
    elif chance==2:
        display(queue)
    elif chance==3:
        delete(queue)
    elif chance==4:
        s=int(input("Enter element to be SEARCHED:"))
        search(queue,s)
    elif chance==5:
        peek(queue)
    elif chance==6:
        break
    else:
        print("You have entered the WRONG INPUT.Try Again.....")
