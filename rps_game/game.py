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
import sys
import subprocess


# ASCII art for moves (right-facing for player)
# More aggressive tilt
FIST_RIGHT = [
    "      ____     ",
    "   ,-(____)-   ",
    " -'  (_____)   ",
    "    (_____)    ",
    "     (____)    ",
    "      (__)     "
]

FIST_LEFT = [
    "     ____      ",
    "   -(____)-,   ",
    "   (_____)  '- ",
    "    (_____)    ",
    "     (____)    ",
    "      (__)     "
]

ROCK_RIGHT = [
    "    _______    ",
    "---'   ____)   ",
    "      (_____)  ",
    "      (_____)  ",
    "      (____)   ",
    "---.__(___)    "
]

PAPER_RIGHT = [
    "     _______     ",
    "---'    ____)____ ",
    "           ______)",
    "          _______)",
    "         _______) ",
    "---.__________)   "
]

SCISSORS_RIGHT = [
    "    _______      ",
    "---'   ____)____ ",
    "          ______)",
    "       __________)",
    "      (____)     ",
    "---.__(___)      "
]

# ASCII art for moves (left-facing for computer)
ROCK_LEFT = [
    "    _______    ",
    "   (____   '---",
    "  (_____)      ",
    "  (_____)      ",
    "   (____)      ",
    "    (___)__.---"
]

PAPER_LEFT = [
    "     _______     ",
    " ____(____    '---",
    "(______           ",
    "(_______          ",
    " (_______         ",
    "   (__________.---"
]

SCISSORS_LEFT = [
    "      _______    ",
    " ____(____   '---",
    "(______          ",
    "(__________       ",
    "     (____)      ",
    "      (___)__.---"
]

ASCII_MOVES_RIGHT = {
    1 : ROCK_RIGHT,
    0 : PAPER_RIGHT,
    -1 : SCISSORS_RIGHT
}

ASCII_MOVES_LEFT = {
    1 : ROCK_LEFT,
    0 : PAPER_LEFT,
    -1 : SCISSORS_LEFT
}

def update_game():
    print("Checking for updates from GitHub...")
    repo_url = "git+https://github.com/SohanurRahmanSohan43/rps_game.git"
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", repo_url])
        print("\n✅ Update complete! Please restart the game to see changes.")
        sys.exit() 
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Update failed: {e}")
        print("Try running the command prompt as Administrator/sudo and try again.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")

def animate_countdown():
    
    for count in ['3', '2', '1', 'SHOOT!']:
        command = 'cls' if os.name == 'nt' else 'clear'
        os.system(command)
        print("\n"*6)
        print(count.center(80))
        sleep(0.5)

def animate_moves(p, c):
    command = 'cls' if os.name == 'nt' else 'clear'
    
    # Calculate final positions
    screen_width = 80
    hand_width = 20
    min_space = 15
    total_hands_width = hand_width * 2 + min_space
    center_padding = (screen_width - total_hands_width) // 2
    
    # Fixed header spacing
    header_spacing = min_space + (12 * 2)
    
    # Hands approach from edges to center
    for distance in range(12, -1, -1):
        os.system(command)
        print("\n"*5)
        
        left_padding = center_padding + (distance * 2)
        right_offset = distance * 2
        
        print(" "*left_padding + "YOU" + " "*header_spacing + "COMPUTER")
        print("=" * 80)

        for p_line, c_line in zip(FIST_RIGHT, FIST_LEFT):
            print(" "*left_padding + p_line + " "*min_space + " "*right_offset + c_line)
        
        print("="*80)
        sleep(distance*0.01)

    sleep(0.2)
    os.system(command)
    print("\n"*5)

    player_lines = ASCII_MOVES_RIGHT[p]
    computer_lines = ASCII_MOVES_LEFT[c]
    
    print(" " * center_padding + "YOU" + " "*header_spacing + "COMPUTER")
    print("="*80)
    
    for p_line, c_line in zip(player_lines, computer_lines):
        print(" " *center_padding + p_line + " " *min_space + c_line)
    print("="*80)
    sleep(1)



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

    animate_countdown()
    animate_moves(p,c)

    value = p-c
    if value in [-1, 2]:
        print("You have won Hurrah!!\n\n".center(80))
        w +=1
    elif value in [1, -2]:
        print("You have lost\n\n".center(80))
        l+=1
    else:
        print("It's a draw!".center(80))
        d+=1
    sleep(1.0)
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
    if len(sys.argv) > 1 and sys.argv[1] in ['--update', '-u']:
        update_game()
    else:
        cli()