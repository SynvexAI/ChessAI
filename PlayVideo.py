import pyglet
from pyglet.window import key
import glob

window = pyglet.window.Window(1280, 720, "Python Player", resizable=True)
window.set_minimum_size(400,300)
songs=glob.glob("./assets/sounds/move.wav")
player=pyglet.media.Player()

@window.event
def on_key_press(symbol, modifiers):
    if symbol == key.ENTER:
        print("A key was pressed")
        @window.event
        def on_draw():
            global player
            for i in range(len(songs)):
                source=pyglet.resource.media(songs[i])
                player.queue(source)
            player.play()

pyglet.app.run()