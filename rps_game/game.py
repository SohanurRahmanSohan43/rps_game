"""
Rock paper scissors game
SCHEME:
rock: 1
paper : 0
scissors: -1

CASES
me computer
1  -1       - win  - 2
1   0       - lose -  1
-1  1       - lose -  -2
-1  0       - win  - -1
0   1       - win - -1
0  -1       - lose - 1

so (-1, 2) for win and (1, -2) for loss

"""
import pyfiglet
from random import choice
from time import sleep
import os
import sys
from rich.console import Console
from rich.table import Table

def get_single_char():

    """Read a single character from stdin without requiring Enter"""

    try:
        # Windows
        import msvcrt
        return msvcrt.getch().decode('utf-8').lower()
    except ImportError:
        # Unix/Linux/Mac
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            char = sys.stdin.read(1).lower()
            return char
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def input_move():
    playerDict = {
                "r": "rock",
                "p": "paper",
                "s": "scissors"
            }
    while True:
        try:
            flush_input()
            print("\n\nChoose any move from below\nr: rock\np: paper\ns: scissors\n\n")
            print("Your move: ", end="", flush=True)
            move = get_single_char()

            if move == "\x03":
                raise KeyboardInterrupt
            if move == "\x04":
                raise EOFError
            
            print(move)

            if move in ['r', 'p', 's']:
                flush_input()
                return playerDict[move]
            else:
                print("Invalid move!\n")

        except(KeyboardInterrupt, EOFError):
            print()
            raise


def win(p, c, w, l, d):
    value = p-c
    if value in [-1, 2]:
        print("You have won Hurrah!!\n\n")
        w +=1
    elif value in [1, -2]:
        print("You have lost\n\n")
        l+=1
    else:
        print("It's a draw!")
        d+=1
    sleep(0.5)
    return(w,l,d)

#To fix the bug while sleep
def flush_input():

    """Flush any pending input from the buffer"""

    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        if not sys.stdin.isatty():
            return
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    movesDict = {
    1 : "rock",
    0 : "paper",
   -1 : "scissors"
}
    noWin, noLose, noDraw = 0, 0, 0
    print("\n\n")

    text = pyfiglet.figlet_format("RPS GAME", font="slant")

    #typewriter animation
    # for char in text:
    #     sys.stdout.write(char)
    #     sys.stdout.flush
    #     sleep(0.001)
    
    #bounce animation
    for i in range (25):
        command = 'cls' if os.name == 'nt' else 'clear'
        os.system(command)
        shifted = "\n".join(" " * i + line for line in text.split("\n"))
        print(shifted)
        sleep(0.04)

    sleep(0.2)
    print("\n\n")
    print("WECOME TO UNLIMITED ROCK PAPER SCISSORS")
    print("="*50)
    print("\n\n")

    while True:

        try:
            compMove = choice([-1, 0, 1])
            flush_input()
            move = input_move()
            playerMove = [key for key, val in movesDict.items() if val == move][0]
            
            print(f"\n\nYou chose {movesDict[playerMove]} and Computer chose {movesDict[compMove]}")
            noWin, noLose, noDraw = win(playerMove, compMove, noWin, noLose, noDraw)


        except (EOFError, KeyboardInterrupt):
            print("\nThanks for playing the game!\n\n")
            console = Console()
            table = Table(title = "SCOREBOARD")
            table.add_column("Wins", style = "Green")
            table.add_column("Loses", style = "Red")   
            table.add_column("Draws", style = "Blue")
            table.add_row(str(noWin), str(noLose), str(noDraw))
            console.print(table)
            print("\n\n")
            break
        
        
def cli():
    main()

if __name__ == "__main__":
    cli()