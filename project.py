class MySQL:
    def __init__(self, a):
        self.a = a

    def Display(self):
        query = "query = select ID, NAME, PRICE, REVIEW.rating from " + self.a + ", REVIEW where ID = code"
        cur.execute(query)
        bK = cur.fetchall()
        if len(bK) == 0:
            print("No Data is Present Here.Insert Some Data.")
        else:
            cur.execute(query)
            table = prettytable.PrettyTable(["Code", "Name", "Price", "Rating"])
            for data in cur.fetchall():
                table.add_row([data[0], data[1], data[2], data[3]])
            print(table)
        db.commit()

    def Insertion(self):
        self.Display()
        l, m = [], []
        try:
            id1 = int(input("Enter ID:"))
            Name = (input("Enter Name:")).upper()
            Price = int(input("Enter Price:"))
            print('' + Style.RESET_ALL)
            query1 = "select* from " + self.a
            cur.execute(query1)
            for data in cur.fetchall():
                l.append(data[2])
            l = len(l)
            query = ("insert IGNORE into " + self.a + "(ID,Name,Price) values({},'{}',{})").format(id1, Name, Price)
            cur.execute(query)
            cur.execute(query1)
            for data in cur.fetchall():
                m.append(data[2])
            m = len(m)
            if l == m:
                print(Fore.RED + "ITEM not added.ID Repeated." + Style.RESET_ALL)
            else:
                print(Fore.RED + "ITEM Successfully added." + Style.RESET_ALL)
            db.commit()
            self.Display()
        except ValueError:
            print(Fore.RED + Style.BRIGHT + "You Have Entered WRONG Choice.Try Again......" + Style.RESET_ALL)

    def Updater(self):
        cur.execute("select * from " + self.a)
        bK = cur.fetchall()
        if len(bK) == 0:
            print("No data is present to be Updated.")
        else:
            l = []
            self.Display()
            try:
                c = int(input("Enter code of Record where data is updated:"))
                cur.execute("select * from " + self.a)
                for data in cur.fetchall():
                    l.append(data[0])
                if c in l:
                    u = (input("Enter Column name where data is updated:")).upper()
                    if u == 'CODE':
                        uv = int(input("Enter Value of data to be changed:"))
                        cur.execute("update " + self.a + " SET ID= {} where ID={}".format(uv, c))
                    elif u == 'PRICE':
                        uv = int(input("Enter Value of data to be changed:"))
                        cur.execute("update " + self.a + " SET PRICE= {} where ID={}".format(uv, c))
                    elif u == 'ITEM NAME' or u == 'NAME':
                        uv = (input("Enter Value of data to be changed:")).upper()
                        cur.execute("update " + self.a + " SET NAME='" + uv + "'where ID={}".format(c))
                    else:
                        print("No such column is present.")
                else:
                    print("Code DOESN'T EXISTS.")
            except ValueError:
                print("You have Entered Wrong Input.")
            except s.errors.IntegrityError:
                print("ID Repeated , Can't update the Record.Try Again......")
            self.Display()
        db.commit()

    def Deletion(self):
        self.Display()
        l, m = [], []
        query1 = "select* from " + self.a
        cur.execute(query1)
        bK = cur.fetchall()
        if len(bK) == 0:
            print("No data is present to be Deleted.")
        else:
            cur.execute(query1)
            for data in cur.fetchall():
                l.append(data[2])
            l = len(l)
            try:
                id1 = int(input("Enter ID of the Record to be Deleted:"))
                query = ("delete from " + self.a + " where ID={}").format(id1)
                cur.execute(query)
                print('')
                cur.execute(query1)
                for data in cur.fetchall():
                    m.append(str(data[2]))
                m = len(m)
                if l == m:
                    print(Fore.RED + "ITEM NOT DELETED.ID DOES'NT EXISTS." + Style.RESET_ALL)
                else:
                    print(Fore.RED + "ITEM DELETED." + Style.RESET_ALL)
                db.commit()
                self.Display()
            except ValueError:
                print(Fore.RED + Style.BRIGHT + "You Have Entered WRONG Choice.Try Again......" + Style.RESET_ALL)

    def Executor(self, i, j, k):  # Function to execute query
        query = "create table if not exists " + self.a + "(\nID int(3) unique not null,\nNAME varchar(50),\nPRICE int(3))"
        cur.execute(query)
        cur.execute(
            ("insert IGNORE into " + self.a + "(ID,NAME,PRICE) values({},'{}',{})").format(i, j, k))
        cur.execute("insert IGNORE into REVIEW(code, TotalCustomer, Rating) values({}, {}, {})".format(i, 0, 0))


def installer():
    import os
    os.system('cmd/c"pip install colorama"')
    os.system('cmd/c"pip install progressbar"')


def repeater(a):
    global keys
    global values
    query = "select ID, NAME, PRICE, REVIEW.rating from " + a + ", REVIEW where ID = code"
    cur.execute(query)
    table = prettytable.PrettyTable(["Code", "Name", "Price", "Rating"])
    for data in cur.fetchall():
        table.add_row([data[0], data[1], data[2], data[3]])
        keys.append(data[1])
        values.append(data[2])
        values.append(data[2])
    print(Fore.CYAN + '')
    print(table)
    print("what do you want to order from above?")


def Repeater(i, Code):
    global bK
    global BV
    global keys
    global values
    global sum1
    global rv
    global qty
    global orderCode
    global code
    q = input("Enter quantity of Your Order you want to have:")
    qty.append(q)
    review = int(input("Review this item out of 5:-"))
    rv.append(review)
    orderCode += (Code + ',')
    bK.append(keys[i])
    BV.append(values[i])
    code.append(Code)
    query = "select TotalCustomer, Rating from Review where code = " + z
    cur.execute(query)
    rating = 0
    for data in cur.fetchall():
        totalCust = int(data[0])
        totalCust += 1
        rating = (float(data[1]) + review)/totalCust
    query = "update Review Set Rating = {} where code = {}".format(rating, z)
    cur.execute(query)
    print("do u want to order anything else?")

def LOADING(bK):  # Function to load the Data
    progress = progressbar.ProgressBar()
    for i in progress(range(80)):
        time.sleep(bK)


def BILLER(name):
    global sum1
    if 0 < len(bK) == len(BV):
        if len(name) == 0:
            billno = 'u0000'
        else:
            no = id(name) + random.randrange(-10000, 10000)
            billno = str(no)[0:8]
        print("BILLNO.   :", billno, "\tCUSTOMER's NAME:", name)
        print(Fore.GREEN + Style.BRIGHT + "YOUR BILL")
        table = prettytable.PrettyTable(["Sr.No", "THINGS YOU ORDERED", "PRICE(Rs)", "QUANTITY", "AMOUNT"])
        for i in range(0, len(bK)):
            sum1 += int(qty[i]) * int(BV[i])
            query = 'update Review SET TotalCustomer = TotalCustomer + 1 where code = {}'.format(code[i])
            cur.execute(query)
            table.add_row([i + 1, bK[i], BV[i], qty[i], int(qty[i]) * int(BV[i])])
        print(table)
    elif len(bK) == 0 or len(BV) == 0:
        print(Fore.RED + "YOU HAVE ORDERED NOTHING" + Style.RESET_ALL)
        billno = 0
    else:
        billno = 0
        print("Something is wrong")
    db.commit()
    return billno


installer()
import progressbar
import time
import mysql.connector as s
import \
    colorama  # COLORAMA IS MODULE WHICH IS USED TO PRINT IN RESPECTIVE COLORS(BLACK,WHITE,CYAN,MAGENTA,BLUE,GREEN,RED,YELLOW)                                                #FORE(PRINTS TEXT FORM) ,BACK(PRINTS BGCOLOR IN PARTICULAR LINE),STYLE(CHANGES SIZE AND TEXTURE OF TEXT)
import random
import sys
import prettytable
from colorama import Fore, Style

# ____MAIN____
colorama.init()  # IT CAN'T BE USED IN SHELL. COLORAMA.INIT() IS USED TO WORK IT WITH PYTHON's DOSON MODE.
print(Fore.YELLOW + '', end='')  # Fore is used to print colored text in py.exe.
orderCode = ''
while True:
    try:
        pwds = input("Enter your MySQL Password to access SQL:")
        db = s.connect(host='localhost', user='root', password=pwds)
        dbs = input("Enter the Database Name To Create:")
        cur = db.cursor()
        cur.execute("create database if not exists " + dbs)
        cur.execute("use " + dbs)  # DATA IS ADDED TO DATABASE IF REQUIRED DATA EXISTS OR NOT.
        cur.execute(
            'create table if not exists REVIEW (code int (3) primary key,\n TotalCustomer int(5),\n Rating Decimal(2, 1))')
        Vc = MySQL('vegcombos')
        Nvc = MySQL('nonvegcombos')
        Vb = MySQL('vegburgers')
        Nvb = MySQL('nonvegburgers')
        O = MySQL('others')
        B = MySQL('beverages')
        D = MySQL('desserts')
        LOADING(0.001)
        Vc.Executor(101, "SHINO BIG SPICY WRAP(V)", 284)
        Vc.Executor(102, "SHINO SPICY(V)", 250)
        Vc.Executor(103, "MAHARAJA SHINO(V)", 292)
        Vc.Executor(104, "SHINO VEGGIE", 197)
        Vc.Executor(105, "SHINO ALOOTIKKI", 148)
        Nvc.Executor(201, "SHINO BIG SPICY WRAP(N)", 289)
        Nvc.Executor(202, "SHINO SPICY(N)", 254)
        Nvc.Executor(203, "MAHARAJA SHINO(N)", 308)
        Nvc.Executor(204, "SHINO CHICKEN", 106)
        Nvc.Executor(205, "CHICKEN KEBAB MEAL", 181)
        Vb.Executor(301, "SHINO BIG SPICY WRAP(V.Bur)", 177)
        Vb.Executor(302, "SHINO SPICY(V.Bur)", 143)
        Vb.Executor(303, "MAHARAJA SHINO(V.Bur)", 185)
        Vb.Executor(304, "SHINO VEGGIE(Bur)", 90)
        Vb.Executor(305, "SHINO ALOOTIKKI(Bur)", 41)
        Nvb.Executor(401, "SHINO BIG SPICY WRAP(N.Bur)", 182)
        Nvb.Executor(402, "SHINO SPICY(N.Bur)", 147)
        Nvb.Executor(403, "MAHARAJA SHINO(N.Bur)", 201)
        Nvb.Executor(404, "SHINO CHICKEN(Bur)", 99)
        Nvb.Executor(405, "CHICKEN KEBAB(Bur)", 74)
        O.Executor(501, "PIRI PIRI", 21)
        O.Executor(502, "CHICKEN NUGGETS(6PCS.)", 123)
        O.Executor(503, "CHICKEN NUGGETS(9PCS.)", 185)
        O.Executor(504, "EGG AND CHEESE SHINO MUFFIN", 68)
        O.Executor(505, "VEG SHINO MUFFIN", 61)
        O.Executor(506, "DOSA MASALA BROICHE", 48)
        B.Executor(601, "SOFT DRINKS(S)", 68)
        B.Executor(602, "SOFT DRINKS(M)", 74)
        B.Executor(603, "SOFT DRINKS(L)", 83)
        B.Executor(604, "COLD COFFEE", 85)
        B.Executor(605, "ICED TEA(R)", 44)
        B.Executor(606, "ICED TEA(M)", 70)
        D.Executor(701, "PHIRNI SHINOFLURRY(R)", 85)
        D.Executor(702, "PHIRNI SHINOFLURRY(M)", 99)
        D.Executor(703, "SHINOFLURRY OREO(R)", 70)
        D.Executor(704, "SHINOFLURRY OREO(M)", 97)
        D.Executor(705, "SHINOCHOCO CRUNCH(R)", 70)
        D.Executor(706, "SHINOCHOCO CRUNCH(M)", 97)
        D.Executor(707, "SOFT SERVE(HOT FLUDGE/STRAWBERRY)", 70)  # Style is used to brigthen or dim text in py.exe
        cur.execute(
            "create table if not exists Customer ( BILLNO varchar(30) primary key,NAME varchar(40),Date date,AMOUNT int(5), ORDER_CODE varchar(40))")
        print(
            Fore.MAGENTA + Style.DIM + ". . . . . . . . . /------------------------------------------\\. . . . . . . . . ")
        print(
            Fore.BLUE + Style.DIM + " . . . . . . . . /-----------WELCOME  TO SHINOPSIS------------\\. . . . . . . . ")
        print(
            Fore.CYAN + Style.DIM + ". . . . . . . . /----------------------------------------------\\. . . . . . . . ")
        print(Fore.GREEN + ". . . . . . . . \----------:-DEVELOPED By SHREY PATEL----------/. . . . . . . . ")
        print(Fore.YELLOW + " . . . . . . . . \--------------------------------------------/. . . . . . . . ")
        print(
            Fore.RED + Style.BRIGHT + ". . . . . . . . . \------------------------------------------/. . . . . . . . . ")
        print(Fore.RED + Style.DIM + "Main Menu" + Style.RESET_ALL)
        while True:
            try:
                print(
                    Fore.GREEN + Style.BRIGHT + "Select Your Choice\n( 1 )ADMIN MENU \n( 2 )CUSTOMER MENU\n( 3 )Exit ")
                f = int(input("Enter Your choice:"))
                if f == 1:  # ADMIN MENU STARTS FROM HERE.
                    pwd = 'PROVIDER'
                    for i in range(0, 2):
                        t = input("ENTER PASSWORD:")
                        if t == pwd:
                            print(Fore.GREEN + "\t\t-------------------------------------------------")
                            print("\t\t--------------WELCOME  TO SHINOPSIS--------------")
                            print("\t\t---------------MANAGEMENT  SYSTEM----------------")
                            print("\t\t-------------------------------------------------")
                            print("\t\t---------------:-By SHREY PATEL------------------")
                            print("\t\t-------------------------------------------------")
                            while True:
                                try:
                                    print("What would like to do now?\n")
                                    print(
                                        "( 1 )Insert Record\n( 2 )Delete Record\n( 3 )Display\n( 4 )Update\n( 5 )Amount Earned on Particular Day\n( 6 )Back to Main Menu\n( 7 ) Exit.")
                                    print(Fore.GREEN + '')
                                    x = int(input("ENTER YOUR CHOICE:"))
                                    print('\n')
                                    if x == 1:  # RECORD IS INSERTED FROM HERE.
                                        while True:
                                            print(
                                                Fore.YELLOW + Style.BRIGHT + "(a)VEG COMBOS\n(b)NON-VEG COMBOS\n(c)VEG BURGERS\n(d)NON-VEG BURGERS\n(e)OTHERS\n(f)BERVERAGES\n(g)DESSERTS\n(h)EXIT" + Style.RESET_ALL)  # STYLE.RESET_ALL(GETS BACK EVERYTHING BACK TO NARMAL)
                                            print(Fore.CYAN + '')
                                            BV = (input("Enter Your choice:")).lower()
                                            if BV == 'a':
                                                Vc.Insertion()
                                            elif BV == 'b':
                                                Nvc.Insertion()
                                            elif BV == 'c':
                                                Vb.Insertion()
                                            elif BV == 'd':
                                                Nvb.Insertion()
                                            elif BV == 'e':
                                                O.Insertion()
                                            elif BV == 'f':
                                                B.Insertion()
                                            elif BV == 'g':
                                                D.Insertion()
                                            elif BV == 'h':
                                                print("Exiting........")
                                                break
                                            else:
                                                print(Fore.RED + "You have Entered Wrong Choice" + Style.RESET_ALL)
                                    elif x == 2:  # RECORDS ARE DELETED FROM HERE.
                                        while True:
                                            print(
                                                Fore.YELLOW + Style.BRIGHT + "(a)VEG COMBOS\n(b)NON-VEG COMBOS\n(c)VEG BURGERS\n(d)NON-VEG BURGERS\n(e)OTHERS\n(f)BERVERAGES\n(g)DESSERTS\n(h)EXIT" + Style.RESET_ALL)
                                            print(Fore.CYAN + '')
                                            BV = (input("Enter Your choice:")).lower()
                                            if BV == 'a':
                                                Vc.Deletion()
                                            elif BV == 'b':
                                                Nvc.Deletion()
                                            elif BV == 'c':
                                                Vb.Deletion()
                                            elif BV == 'd':
                                                Nvb.Deletion()
                                            elif BV == 'e':
                                                O.Deletion()
                                            elif BV == 'f':
                                                B.Deletion()
                                            elif BV == 'g':
                                                D.Deletion()
                                            elif BV == 'h':
                                                print("Exiting........")
                                                break
                                            else:
                                                print(Fore.RED + "You have Entered Wrong Choice" + Style.RESET_ALL)
                                    elif x == 3:
                                        while True:
                                            print(
                                                Fore.YELLOW + Style.BRIGHT + "(a)VEG COMBOS\n(b)NON-VEG COMBOS\n(c)VEG BURGERS\n(d)NON-VEG BURGERS\n(e)OTHERS\n(f)BERVERAGES\n(g)DESSERTS\n(h)EXIT" + Style.RESET_ALL)
                                            print(Fore.CYAN + '')
                                            BV = (input("Enter Your choice:")).lower()
                                            if BV == 'a':
                                                Vc.Display()
                                            elif BV == 'b':
                                                Nvc.Display()
                                            elif BV == 'c':
                                                Vb.Display()
                                            elif BV == 'd':
                                                Nvb.Display()
                                            elif BV == 'e':
                                                O.Display()
                                            elif BV == 'f':
                                                B.Display()
                                            elif BV == 'g':
                                                D.Display()
                                            elif BV == 'h':
                                                print("Exiting........")
                                                break
                                            else:
                                                print(Fore.RED + "You have Entered Wrong Choice" + Style.RESET_ALL)
                                    elif x == 4:
                                        while True:
                                            print(
                                                Fore.YELLOW + Style.BRIGHT + "(a)VEG COMBOS\n(b)NON-VEG COMBOS\n(c)VEG BURGERS\n(d)NON-VEG BURGERS\n(e)OTHERS\n(f)BERVERAGES\n(g)DESSERTS\n(h)EXIT" + Style.RESET_ALL)
                                            print(Fore.CYAN + '')
                                            BV = (input("Enter Your choice:")).lower()
                                            if BV == 'a':
                                                Vc.Updater()
                                            elif BV == 'b':
                                                Nvc.Updater()
                                            elif BV == 'c':
                                                Vb.Updater()
                                            elif BV == 'd':
                                                Nvb.Updater()
                                            elif BV == 'e':
                                                O.Updater()
                                            elif BV == 'f':
                                                B.Updater()
                                            elif BV == 'g':
                                                D.Updater()
                                            elif BV == 'h':
                                                print("Exiting........")
                                                break
                                            else:
                                                print(Fore.RED + "You have Entered Wrong Choice" + Style.RESET_ALL)
                                    elif x == 5:
                                        sum2 = 0
                                        date1 = input("Enter date in YYYY-MM-DD format:")
                                        cur.execute("select * from Customer where Date='{}'".format(date1))
                                        BV = cur.fetchall()
                                        if len(BV) > 0:
                                            table = prettytable.PrettyTable(["Bill No.", "Name", "Date", "Amount", "Order Code Given"])
                                            cur.execute("select * from Customer where Date='{}'".format(date1))
                                            for data in cur.fetchall():
                                                table.add_row([data[0], data[1], data[2], data[3], data[4]])
                                                sum2 += data[3]
                                            print(table)
                                            print("Total : " + str(sum2))
                                        elif len(BV) == 0:
                                            print("No Data is present to Show.")
                                        db.commit()
                                    elif x == 7:
                                        print("Exiting.........")
                                        db.commit()
                                        db.close()
                                        LOADING(0.01)
                                        exit()
                                    elif x >= 8:
                                        print(
                                            Fore.RED + Style.BRIGHT + "You Have Entered WRONG Choice.Try Again......" + Style.RESET_ALL)
                                        print(Fore.GREEN + '')
                                    if x == 6:
                                        print(Fore.RED + Style.BRIGHT + "Exiting..........." + Style.RESET_ALL)
                                        LOADING(0.01)
                                        break
                                except ValueError:
                                    print(
                                        Fore.RED + Style.BRIGHT + "You Have Entered WRONG INPUT.Try Again......" + Style.RESET_ALL)
                                    print(Fore.GREEN + '')
                                except s.errors.DatabaseError:
                                    print(
                                        Fore.RED + Style.BRIGHT + "You Have Entered WRONG INPUT.Try Again......" + Style.RESET_ALL)
                                    print(Fore.GREEN + '')
                            break
                        else:  # EXITS FROM ADMIN MENU AND FROM THE SYSTEM ALSO.
                            db.commit()
                            print(Fore.RED + Style.BRIGHT + "YOU HAVE ENTERED WRONG PASSWORD.TRY AGAIN............")
                elif f == 2:  # CUSTOMER MENU STARTS FROM HERE.
                    print(Fore.GREEN + "\t\t-------------------------------------------------")
                    print("\t\t--------------WELCOME  TO SHINOPSIS--------------")
                    print("\t\t----------------EATCORNER  CENTRE----------------")
                    print("\t\t-------------------------------------------------")
                    print("\t\t---------------:-By SHREY PATEL------------------")
                    print("\t\t-------------------------------------------------")
                    a = 0
                    sum1 = 0
                    bK = []
                    BV = []
                    qty = []
                    rv = []
                    code = []
                    name = str(input("Enter Your name:"))
                    print("what would you like to eat for your meal?")
                    while True:
                        try:
                            print('\n')
                            print(
                                Fore.YELLOW + Style.DIM + "(00)FINAL BILLING\n(01)VEG COMBOS\n(02)NON-VEG COMBOS\n(03)VEG BURGERS\n(04)NON-VEG BURGERS\n(05)OTHERS\n(06)BERVERAGES\n(07)DESSERTS\n(08)BILLING\n(09)MISORDER\n(10)Back To Main Menu\n(11)Exit.\n")
                            x = input("Enter your Choice:")
                            keys = []
                            values = []
                            if x == '01' or x == '1':  # VEG-COMBO MENU
                                a = "vegcombos"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '101':
                                        Repeater(0, '101')
                                    elif z == '102':
                                        Repeater(1, '102')
                                    elif z == '103':
                                        Repeater(2, '103')
                                    elif z == '104':
                                        Repeater(3, '104')
                                    elif z == '105':
                                        Repeater(4, '105')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '02' or x == '2':  # NON-VEG-COMBO MENU
                                a = "nonvegcombos"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '201':
                                        Repeater(0, '201')
                                    elif z == '202':
                                        Repeater(1, '202')
                                    elif z == '203':
                                        Repeater(2, '203')
                                    elif z == '204':
                                        Repeater(3, '204')
                                    elif z == '205':
                                        Repeater(4, '205')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '03' or x == '3':  # VEG-BURGER MENU
                                a = "vegburgers"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '301':
                                        Repeater(0, '301')
                                    elif z == '302':
                                        Repeater(1, '302')
                                    elif z == '303':
                                        Repeater(2, '303')
                                    elif z == '304':
                                        Repeater(3, '304')
                                    elif z == '305':
                                        Repeater(4, '305')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '04' or x == '4':  # NON-VEG BURGER MENU
                                a = "nonvegburgers"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '401':
                                        Repeater(0, '401')
                                    elif z == '402':
                                        Repeater(1, '402')
                                    elif z == '403':
                                        Repeater(2, '403')
                                    elif z == '404':
                                        Repeater(3, '404')
                                    elif z == '405':
                                        Repeater(4, '405')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '05' or x == '5':  # EXTRA'S MENU
                                a = "others"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '501':
                                        Repeater(0, '501')
                                    elif z == '502':
                                        Repeater(1, '502')
                                    elif z == '503':
                                        Repeater(2, '503')
                                    elif z == '504':
                                        Repeater(3, '504')
                                    elif z == '505':
                                        Repeater(4, '505')
                                    elif z == '506':
                                        Repeater(5, '506')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '06' or x == '6':  # BEVERAGE'S MENU
                                a = "beverages"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '601':
                                        Repeater(0, '601')
                                    elif z == '602':
                                        Repeater(1, '602')
                                    elif z == '603':
                                        Repeater(2, '603')
                                    elif z == '604':
                                        Repeater(3, '604')
                                    elif z == '605':
                                        Repeater(4, '605')
                                    elif z == '606':
                                        Repeater(5, '606')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '07' or x == '7':  # DESSERT'S MENU
                                a = "desserts"
                                repeater(a)
                                while True:
                                    z = input("Enter Code to order or Press 'N' or 'n' to EXIT:")
                                    if z == '701':
                                        Repeater(0, '701')
                                    elif z == '702':
                                        Repeater(1, '702')
                                    elif z == '703':
                                        Repeater(2, '703')
                                    elif z == '704':
                                        Repeater(3, '704')
                                    elif z == '705':
                                        Repeater(4, '705')
                                    elif z == '706':
                                        Repeater(5, '706')
                                    elif z == '707':
                                        Repeater(6, '707')
                                    elif z == 'n' or z == 'N':
                                        break
                                    else:
                                        print("You have Entered Wrong INPUT.TRY AGAIN ........")
                            elif x == '08' or x == '8':  # PRINTS CURRENT BILL.
                                BILLER(name)
                            elif x == '09' or x == '9':  # ELIMINATES A CHOSEN ORDER BY CUSTOMER.
                                try:
                                    BILLER(name)
                                    print("What would u like to remove from this List?")
                                    c = int(input("Enter the number of order you want to remove:"))
                                    q = input("Enter quantity of order you want to remove:")
                                    z = int(qty[c - 1])
                                    t = int(q)
                                    if t <= z:
                                        d = z - t
                                        sum1 -= int(q) * BV[c - 1]
                                        qty.pop(c - 1)
                                        if d == 0:
                                            bK.pop(c - 1)
                                            BV.pop(c - 1)
                                        else:
                                            qty.insert(c - 1, str(d))
                                        BILLER(name)
                                    else:
                                        print(
                                            "QUANTITY THAT YOU WANT TO REMOVE IS MORE THEN WHAT YOU HAVE ORDERED FOR.")
                                except IndexError:
                                    print("There is no such order that You want to Delete from your List.")
                            elif x == '10':  # EXITS FROM CUSTOMER MENU AND ALSO FROM THE SYSTEM
                                billno = BILLER(name)
                                if billno != 0:
                                    cur.execute(
                                        "insert IGNORE into Customer(BILLNO,NAME,DATE,AMOUNT,ORDER_CODE) values({},'{}',CURDATE(),{},'{}')".format(
                                            billno, name, sum1, orderCode[0:len(orderCode) - 1]))
                                db.commit()
                                break
                            elif x == '00' or x == '0':  # RECORDS OF PREVIOUS CUSTOMER ARE DELETED FROM HERE.
                                billno = BILLER(name)
                                cur.execute(
                                    "insert IGNORE into Customer(BILLNO,NAME,DATE,AMOUNT,ORDER_CODE) values({},'{}',CURDATE(),{},'{}')".format(
                                        billno, name, sum1, orderCode[0:len(orderCode) - 1]))
                                db.commit()
                                print(Fore.RED + "RECORD OF PREVIOUS CUSTOMER IS DELETED.\n" + Style.RESET_ALL)
                                print(
                                    Fore.MAGENTA + Style.DIM + ". . . . . . . . . /------------------------------------------\\. . . . . . . . . ")
                                print(
                                    Fore.BLUE + Style.DIM + " . . . . . . . . /-----------WELCOME  TO SHINOPSIS------------\\. . . . . . . . ")
                                print(
                                    Fore.CYAN + Style.DIM + ". . . . . . . . /------------------CORPORATE-------------------\\. . . . . . . . ")
                                print(
                                    Fore.GREEN + ". . . . . . . . \----------:-DEVELOPED By SHREY PATEL----------/. . . . . . . . ")
                                print(
                                    Fore.YELLOW + " . . . . . . . . \--------------------------------------------/. . . . . . . . ")
                                print(
                                    Fore.RED + Style.BRIGHT + ". . . . . . . . . \------------------------------------------/. . . . . . . . . ")
                                sum1 = 0
                                bK.clear()
                                keys.clear()
                                values.clear()
                                BV.clear()
                                qty.clear()
                                rv.clear()
                                code.clear()
                                orderCode = ''
                                name = input("Enter your name:")
                            elif x == '11':
                                billno = BILLER(name)
                                if billno != 0:
                                    cur.execute(
                                        "insert IGNORE into Customer(BILLNO,NAME,DATE,AMOUNT,ORDER_CODE) values({},'{}',CURDATE(),{},'{}')".format(
                                            billno, name, sum1, orderCode[0:len(orderCode) - 1]))
                                print("Exiting........")
                                LOADING(0.1)
                                db.commit()
                                db.close()
                                sys.exit()
                            else:
                                print(Fore.RED + "\nYOU HAVE ENTERED WRONG CHOICE. TRY AGAIN . . . . . . . . .\n")
                                print("WHAT IS YOUR CHOICE?" + Style.RESET_ALL)
                        except ValueError:
                            print(Fore.RED + "\nYOU HAVE ENTERED WRONG INPUT. TRY AGAIN . . . . . . . . .\n")
                            print("WHAT IS YOUR CHOICE?" + Style.RESET_ALL)
                elif f == 3:
                    db.commit()
                    print(Fore.RED + "Exiting...." + Style.RESET_ALL)
                    LOADING(0.01)
                    db.close()
                    sys.exit()
                else:
                    print('')
                    print(Fore.RED + Style.BRIGHT + "You Have Entered WRONG Choice.Try Again......" + Style.RESET_ALL)
                    print(Fore.GREEN + '')
            except ValueError():
                print('')
                print(Fore.RED + Style.BRIGHT + "You Have Entered WRONG INPUT.Try Again......" + Style.RESET_ALL)
                print(Fore.GREEN + '')
    except s.errors.InterfaceError:
        print(Fore.RED + "PLEASE CHECK WHETHER MySQL SERVER IS STARTING OR NOT." + Style.RESET_ALL)
    except s.errors.ProgrammingError:
        print(Fore.RED + "ENTER YOUR MySQL PASSWORD CORRECTLY.TRY AGAIN!!!!!!" + Style.RESET_ALL)
