from ursina import *
app = Ursina()

cube=Entity(model = 'cube', color=color.red, texture="brick", scale=4)
def update():
    cube.rotation_x+=0.25
    cube.rotation_y+=0.5

app.run()
