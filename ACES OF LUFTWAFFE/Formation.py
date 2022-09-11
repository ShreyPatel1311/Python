'''654321
    4321
     21'''
import pygame
running=True
screen = pygame.display.set_mode((600,800))
enemyIMG = []
playerIMG = pygame.image.load('jet.png')
while running:
    screen.fill((0,0,255))
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running=False
    n=4
    x=n*64
    for i in range(64,448,64):
        for j in range(0,i,64):
            print(" ",end=' ')
        for k in range(x,0,-64):
            print(k,end=' ')
            enemyIMG.append(pygame.image.load('enemy.png'))
            o=int(k/64)
            screen.blit(enemyIMG[0],(264-i,k-60))
        for l in range(k,0,-64):
            print(l,end=' ')
            x-=64
        for m in range(x+64,0,-64):
            print(m,end=' ')
            screen.blit(enemyIMG[0],(i+264,m-60))
        print()
    pygame.display.update()
