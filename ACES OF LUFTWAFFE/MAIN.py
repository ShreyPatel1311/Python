#Double Loop in gameloop
#Highest Score printing + Score storing in MySQL 
#Correction in Formation
def isCollision(enemyX,enemyY,bulletX,bulletY):
    import math
    d=math.sqrt((math.pow(enemyX-bulletX,2))+math.pow(enemyY-bulletY,2))
    if d<32:
        return True
    else:
        return False
def gameloop():
    import pygame
    import random
    import math

    pygame.init()


    screen = pygame.display.set_mode((600,800))
    icon=pygame.image.load('icon.png')
    pygame.display.set_caption("ACES OF LUFTWAFFE")
    pygame.display.set_icon(icon)
    playerX=270
    playerY=700
    playerIMG = pygame.image.load('jet.png')
    xp=0

    enemyX=[]
    enemyY=[]
    enemyIMG = []
    xe=[]
    EbulletX=[]
    EbulletY=[]
    EbulletIMG=[]
    count=0
    n=12
    for i in range(n):
        for j in range(i):
            enemyX.append(i*64)
            enemyY.append(j*64)
            enemyIMG.append(pygame.image.load('enemy.png'))
            xe.append(0.4)
            EbulletX.append(enemyX[j])
            EbulletY.append(enemyY[j])
            EbulletIMG.append(pygame.image.load('hurricane.png'))

    pygame.mixer.music.load('fighter_plane_squadron-Mike_Koenig-1917709101.wav')
    pygame.mixer.music.play(-1)

    score=0
    
    font=pygame.font.Font("freesansbold.ttf",32)
    textX=150
    textY=399

    bulletX=0
    bulletY=700
    bulletIMG =pygame.image.load('bullet.png')
    bullet_state = "ready"
    xb=0
    yb=-0.4

    collisionIMG=pygame.image.load('explosion.png')
    running=True
    while running:
        screen.fill((0,125,255))
        if bullet_state is "fire":
            bulletY-=0.4
        elif bullet_state is "ready":
            bulletY=700
            bulletY+=0
            bulletX=playerX
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running=False
        #PLAYER MOVEMENT
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                xp=-0.2
            elif event.key == pygame.K_RIGHT:
                xp=0.2
            elif event.key == pygame.K_UP:
                bullet_state="fire"
        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_LEFT:
                xp=-0.2
            elif event.key == pygame.K_RIGHT:
                xp=0.2
            elif event.key == pygame.K_UP:
                bullet_state="fire"

        playerX+=xp
        if playerX<=0:
            playerX=0
        elif playerX>=486:
            playerX=486

        #Enemy Movement
        for i in range(n):
            EbulletY[i]+=0.4
            enemyX[i]+=(xe[i])
            if enemyX[i]<=50:
                xe[i]=0.4
            elif enemyX[i]>=486:
                xe[i]=-0.4
            if EbulletY[i]>824:
                EbulletY[i]=enemyY[i]
                EbulletX[i]=enemyX[i]
            collision=isCollision(enemyX[i],enemyY[i],bulletX,bulletY)
            if collision is True:
                screen.blit(collisionIMG,(enemyX[i],enemyY[i]))
                bulletY=700
                bullet_state = "ready"
                score+=10
                enemyX[i]=536
                enemyY[i]=10000
                count+=1
                if count==n:
                    l.append(score)
                    for i in range(len(l)):
                        score+=l[i]
                    gameloop()
                    running=False
            screen.blit(enemyIMG[i],(enemyX[i],enemyY[i]))
            screen.blit(EbulletIMG[i],(EbulletX[i]+19,EbulletY[i]+5))
            Ecollision=isCollision(playerX,playerY,EbulletX[i],EbulletY[i])
            if Ecollision is True:
                screen.blit(collisionIMG,(playerX,playerY))
                s=font.render(" SCORE : "+str(score),True,(255,0,0))
                t=font.render("GAME OVER",True,(255,0,0))
                screen.blit(s,(textX,textY))
                screen.blit(t,(textX,textY+49))
                running = False
                
        #Bullet Movement
        bulletY+=yb
        if bulletY <= -16:
            bulletY=700
            bullet_state="ready"
        
        screen.blit(bulletIMG,(bulletX+19,bulletY+5))
        screen.blit(bulletIMG,(bulletX+8,bulletY+10))
        screen.blit(bulletIMG,(bulletX+30,bulletY+10))
        screen.blit(playerIMG,(playerX,playerY))
        pygame.display.update()
import os
os.system('cmd\c"pip install pygame"')
gameloop()
