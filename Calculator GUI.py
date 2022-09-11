from tkinter import *
import os
os.system('cmd/c"pip install pillow"')
from PIL import ImageTk,Image

def mySwitch(i):
    f=e.get()
    e.delete(0, END)
    e.insert(0, f+str(i))

def addition():
    global f_num
    global maths
    maths="addition"
    first_number=e.get()
    f_num=int(first_number)
    e.delete(0, END)

def multiplication():
    global f_num
    global maths
    maths="multiplication"
    first_number=e.get()
    f_num=int(first_number)
    e.delete(0, END)
    
def division():
    global f_num
    global maths
    maths="division"
    first_number=e.get()
    f_num=int(first_number)
    e.delete(0, END)

def square():
    global f_num
    first_number=e.get()
    f_num=int(first_number)
    e.delete(0, END)
    e.insert(0,(f_num*f_num))

def clear():
    e.delete(0, END)

def equal():
    global maths
    sec_num=int(e.get())
    e.delete(0, END)
    if maths=="addition":
        result=f_num+sec_num
    elif maths=="Subtraction":
        result=f_num-sec_num
    elif maths=="multiplication":
        result=f_num*sec_num
    elif maths=="division":
        result=f_num/sec_num
    else:
        result=sec_num
    e.insert(0,result)
    
root=Tk()
root.title("SIMPLE CALCULATOR")
maths=""
e = Entry(root,borderwidth=3,bg="cyan",fg="white",width=65)
e.grid(row=0,column=0,columnspan=4)

button_1 = Button(root,text="1",padx=40,pady=20,command=lambda:mySwitch(1))
button_2 = Button(root,text="2",padx=40,pady=20,command=lambda:mySwitch(2))
button_3 = Button(root,text="3",padx=40,pady=20,command=lambda:mySwitch(3))
button_4 = Button(root,text="4",padx=40,pady=20,command=lambda:mySwitch(4))
button_5 = Button(root,text="5",padx=40,pady=20,command=lambda:mySwitch(5))
button_6 = Button(root,text="6",padx=40,pady=20,command=lambda:mySwitch(6))
button_7 = Button(root,text="7",padx=40,pady=20,command=lambda:mySwitch(7))
button_8 = Button(root,text="8",padx=40,pady=20,command=lambda:mySwitch(8))
button_9 = Button(root,text="9",padx=40,pady=20,command=lambda:mySwitch(9))
button_0 = Button(root,text="0",padx=90,pady=20,command=lambda:mySwitch(0))
button_sub = Button(root,text="-",padx=40,pady=20,command=addition)
button_div = Button(root,text="/",padx=40,pady=20,command=division)
button_mul = Button(root,text="*",padx=40,pady=20,command=multiplication)
button_squ = Button(root,text="x^2",padx=40,pady=20,command=square)
button_add = Button(root,text="+",padx=40,pady=20,command=addition)
button_equal = Button(root,text="=",padx=45,pady=20,command=equal)
button_clear = Button(root,text="Clear",padx=35,pady=86,command=clear)

button_1.grid(row=1,column=0)
button_2.grid(row=1,column=1)
button_3.grid(row=1,column=2)

button_4.grid(row=2,column=0)
button_5.grid(row=2,column=1)
button_6.grid(row=2,column=2)

button_7.grid(row=3,column=0)
button_8.grid(row=3,column=1)
button_9.grid(row=3,column=2)

button_0.grid(row=4,column=1,columnspan=2)

button_sub.grid(row=5,column=0)
button_div.grid(row=5,column=1)
button_mul.grid(row=5,column=2)
button_squ.grid(row=5,column=3)
button_add.grid(row=4,column=0)
button_equal.grid(row=1,column=3)
button_clear.grid(row=2,column=3,rowspan=3)

root.mainloop()
