import pygame
pygame.init()
move_sound = pygame.mixer.Sound("Chess.com AI/assets/sounds/move.wav")

if True:
    print("Условие выполнено, воспроизведение звука.")
    move_sound.play()

    while pygame.mixer.get_busy():
        pygame.time.delay(100)


pygame.quit()