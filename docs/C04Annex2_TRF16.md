# C.04 Annex 2 TRF16 (Converted)

Source: https://www.fide.com/FIDE/handbook/C04Annex2_TRF16.pdf

Retrieved: 2026-03-07

Conversion: pdftotext from the official PDF, then light cleanup (page breaks to horizontal rules).

## Notes

- In the player-round triplet, positions 92-95 can be four blanks (equivalent to 0000) for bye/not-paired.
- Position 97 can be blank (equivalent to '-').
- Position 99 can be blank (equivalent to 'Z').
- This is the authoritative text snapshot for local parser discussions.

---

Format of TRF (Tournament Report File)
Agreed general Data-Exchange Format for tournament results to be submitted to FIDE.
Remark 1 Each line shall have a "CR" (carriage return) as last character
Remark 2 The columns R and P in all the following tables tell the
importance of the field for Rating and Pairing respectively

■
□

Mandatory
Warning if wrong
Not taken into account

Player Section
Position

1
5
10
11
15
49
54
58
70
81

-

Description

Contents

3 DataIdentificationnumber
8 Startingrank-Number
Sex
13 Title
47 Name
52 FIDE Rating
56 FIDE Federation
68 FIDE Number
79 Birth Date
84 Points

001 (for player-data)
from 1 to 9999
m/w
GM, IM, WGM, FM, WIM, CM, WFM, WCM
Lastname, Firstname

(including 3 digits reserve)
Format: YYYY/MM/DD
Points (in the format 11.5)

R P
■ ■
■ ■
□
□
□
□
□
■
□
■

This is the number of points in the tournament standings, which depends on the scoring
points system used and on the value of the pairing-allocated bye (usually the same as a
win). If, for instance, the 3/1/0 scoring point system is applied in a tournament and a
player scored 5 wins, 2 draws and 2 losses, this field should contain "17.0"

86 - 89 Rank

Exact definition, especially for Team

■

For each round:
Position

Description

92

Player or forfeit id
in round 1

97

99

- 95

Contents
____ Startingrank-Number of the scheduled opponent (up to 4
digits)
0000 If the player had a bye (either half-point bye, full-point bye
or odd-number bye) or was not paired (absent, retired, not
nominated by team)
(four blanks) equivalent to 0000

Scheduled color or
forfeit in round 1

w
b
-

Result of round 1

The scheduled game was not played
- forfeit loss
+ forfeit win
The scheduled game lasted less than one move
W win
Not rated
D draw
Not rated
L loss
Not rated
Regular game
1 win
= draw
0 loss
Bye
H half-point-bye
Not rated
F full-point-bye
Not rated
U pairing-allocated bye
At most once for round - Not rated
(U for player unpaired by the system)
Z zero-point-bye
Known absence from round - Not rated
(blank) equivalent to Z

R P

■

■

■

■

■

■

Scheduled color against the scheduled opponent
(minus) If the player had a bye or was not paired
(blank) equivalent to -

Note: Letter codes are case-insensitive (i.e. w,d,l,h,f,u,z can be used)



---

102 - 105 Id
107
Color
109
Result

Round 2 (analog to round 1)

■
■
■

■
■
■

112 - 115 Id
117
Color
119
Result
and so on...

Round 3 (analog to round 1)

■
■
■

■
■
■

Tournament Section
Data-Identification-number (??2 for tournament data)
position 1-3

from position 5 (free text)

012
022
032
042
052
062
072
082
092
102
112
122
132

Tournament Name
City
Federation
Date of start
Date of end
Number of players
Number of rated players
Number of teams
in case of a team tournament
Type of tournament
Chief Arbiter
Deputy Chief Arbiter
one line for each arbiter
Allotted times per moves/game
Dates of the round
format: YY/MM/DD
Position

R P
■ ■
■
■

■

Description

92 - 99 Round 1 date
102 - 109 Round 2 date
112 - 119 Round 3 date
and so on...

Team Section
Position

Description

Contents

1
- 3
Team-Section-Identifier 013 (for team data)
5
- 36 Team Name
37 - 40 Team 1st player
42 - 45 Team 2nd player
47 - 50 Team 3rd player
(continue, if needed)
StartingRank Number from Player Section (position 5-8)
72 - 75 Team 8th player
(continue, if needed)
102 - 105 Team 14th player
(and so on)

Christian Krause (Torino, June 1st, 2006)
Updated: Tromsø, August 13th, 2014
Approved: Elista, August 10th, 2015

R P
■ ■
■ ■

■

■



---

