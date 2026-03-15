# C.04.4.1 Dubov System (effective till 31 January 2026)

Source: https://handbook.fide.com/chapter/C040401Till2026

Retrieved: 2026-03-15

*Approved by the 2018 General Assembly.*

*The Dubov Swiss Pairing System is designed to maximise the fair treatment of the players. This means that a player having more points than another player during a tournament should have a higher performance rating as well.*
*If the average rating of all players is nearly equal, like in a round robin tournament, the goal is reached. As a Swiss System is a statistical system, this goal can only be reached approximately. The approach is the attempt to equalise the average rating of the opponents (ARO, see A.6) of all players of a scoregroup. Therefore, the pairing of a round will now pair players who have a low*
*ARO against opponents having high ratings.*

**A Introductory Remarks and Definitions**

**A.1 Rating**
Each player must have a rating. If a player does not have a rating, a provisional one must be assigned to the player by the arbiter.

**A.2 Initial ranking list**
See C.04.2.B (General Handling Rules - Initial order)
Each time a player's rating is introduced or modified before the pairing of the fourth round, the arbiter must re-sort the initial ranking list according to the aforementioned section.

**A.3 Scoregroups and pairing brackets**
A scoregroup is composed of all the players with the same score.
A (pairing) bracket is a group of players to be paired. It is composed of players coming from the same scoregroup (called resident players) and (possibly) of players coming from lower scoregroups (called upfloaters).
*Note: Unlike other systems, there are no downfloaters in the Dubov System.*

**A.4 Byes**
See C.04.1.c *(Should the number of players to be paired be odd, one player is unpaired. This player receives a pairing-allocated bye: no opponent, no colour and as many points as are rewarded for a win, unless the regulations of the tournament state otherwise)*.

**Colour differences and colour preferences**
The colour difference of a player is the number of games played with white minus the number of games played with black by this player.
The colour preference *(also called: **due colour**)* is the colour that a player should ideally receive for the next game.
a. An absolute colour preference occurs when a player's colour difference is greater than +1 or less than -1, or when a player had the same colour in the two latest rounds he played. The preference is white when the colour difference is less than -1 or when the last two games were played with black. The preference is black when the colour difference is greater than +1, or when the last two games were played with white.
b. A strong colour preference occurs when a player's colour difference is +1 (preference for black) or -1 (preference for white).
c. A mild colour preference occurs when a player's colour difference is zero, the preference being to alternate the colour with respect to the previous game he played.
d. Players who did not play any games are considered to have a mild colour preference for black.

**Average Rating of Opponents (ARO)**
ARO is defined for each player who has played at least one game. It is given by the sum of the ratings of the opponents the player met over-the-board *(i.e. only played games are used to compute ARO)*, divided by the number of such opponents, and rounded to the nearest integer number (the higher, if the division ends for 0.5).
ARO is computed for each player after each round as a basis for the pairings of the next round.
If a player has yet to play a game, his ARO is zero.

**Maximum upfloater**
A player is said to be a maximum upfloater when he has already been upfloated a maximum number of times (MaxT).
MaxT is a parameter whose value depends on the number of rounds in the tournament (Rnds), and is computed with the following formula:
**MaxT = 2 + [Rnds/5]**
where [Rnds/5] means Rnds divided by 5 and rounded downwards.

**Round-Pairing Outlook**
The pairing of a round (called round-pairing) is complete if all the players (except at most one, who receives the pairing-allocated bye) have been paired and the absolute criteria C1-C3 have been complied with.
The pairing process starts with the assignment of the pairing-allocated-bye *(see B.0)* and continues with the pairing of all the scoregroups *(see B.1)*, in descending order of score, until the round-pairing is complete.
If it is impossible to complete a round-pairing, the arbiter shall decide what to do. Section B describes the pairing procedures.
Section C defines all the criteria that the pairing of a bracket has to satisfy (in
order of priority).
Section E defines the colour allocation rules that determine which players will play with White.

The pairing-allocated-bye is assigned to the player who:
a. has neither received a pairing-allocated-bye, nor scored a (forfeit) win in the previous rounds (see C.2)
b. allows a complete pairing of all the remaining players (see C.4)
c. has the lowest score
d. has played the highest number of games
e. occupies the lowest position in the initial ranking list (see A.2)

Determine the minimum number of upfloaters needed to obtain a legal pairing of all the (remaining) resident players of the scoregroup.
*Note: A pairing is legal when the criteria C.1, C.3 and C.4 are complied with.*

Choose the first set of upfloaters (first in the order given by rule D.1) that, together with the (remaining) resident players of this scoregroup, produces a pairing that complies at best with all the pairing criteria (C.1 to C.10).
*Note: In order to choose the best set of upfloaters, consider that the ensuing bracket (residents + upfloaters) is paired better than another one if it better satisfies a quality criterion (C.5-C.10) of higher priority.*

The players of the bracket are divided in two subgroups:
G1 This subgroup initially contains the players who have a colour preference for White, unless all the players in the bracket have yet to play a game *(like, for instance, in the first round)*. In the latter case, this subgroup contains the first half of the players of the bracket (according to the initial ranking list).
G2 This subgroup initially contains the remaining players of the bracket.

If players from the smaller subgroup (or from G1, if their sizes are equal) must unavoidably be paired together, a number of players equal to the number of such pairs must be shifted from that subgroup into the other one. Find the *best* set of such players and proceed with the shift.
Now, if the number of players in (the possibly new) G1 is different from the number of players in (the possibly new) G2, in order to equalize the size of the two subgroups, extract the *best* set of players from the larger subgroup, and shift those players into the smaller subgroup.
*Note: *Best*, in both instances, means the first set of players (first in the order given by rule D.2) that can yield a legal pairing that complies at best with C.7.*

Sort the players in (the possibly new) G1 in order of ascending ARO or, when AROs are equal, according to the initial ranking list - highest initial ranking first and so on.
S1 is the subgroup resulting from such sorting.
*Note: The sorting of G2 players is described in D.3.*

Choose T2, which is the first such transposition of G2 players (transpositions are sorted by rule D.3) that can yield a legal pairing, according to the following generation rule: the first player of S1 is paired with the first player of T2, the second player of S1 with the second player of T2, and so on.

**C Pairing Criteria**

**Absolute Criteria** No pairing shall violate the following absolute criteria:

C.1 see C.04.1.b *(Two players shall not play against each other more than once)*

see C.04.1.d *(A player who has already received a pairing-allocated bye, or has already scored a (forfeit) win due to an opponent not appearing in time, shall not receive the pairing-allocated bye)*.

C.3 two players with the same absolute colour preference (see A.5.a) shall not meet (see C.04.1.f and C.04.1.g).

**Completion Criterion**

**C.4**

**Quality Criteria**
To obtain the best possible pairing for a bracket, comply as much as possible with the following criteria, given in descending priority:

**Generalities**
*In the articles of this section, the schema below is followed:*
a. *A pool of P players is selected.*
b. *Each player in the pool is assigned a sequence number (from #1 to #P) according to a primary sorting criterion.*
c. *In order to select a set of K such players, the sets will usually be sorted depending on the sequence numbers of their members, put in lexicographic order (exception is D.1.b). For instance, with K=2, the set {#1,#2} will precede {#1,#3}, the set {#1,#P} will precede {#2,#3}, and so on.*
*Note. The term *initial ranking *always refers to the definition in section C.04.2.B, stating that the highest ranked player is first and the lowest ranked player is last.*

**Sorting the upfloaters**
*All those players that have a lower score than the resident players of the scoregroup to be paired, are possible upfloaters and constitute the selected pool (see D.0.a).*
a. Main criterion
Each possible upfloater receives a sequence number, according to their score and, when scores are equal, to their initial ranking.
b. Sets of upfloaters
Because a set of upfloaters may be formed of players with different scores, all the possible sets are subdivided in containers. Sets belong to the same container if their players have the same scores.

*Example:*
*Let's assume that #1,#2,#3 have 3 points, #4 and #5 have 2.5 points, and #6 has*
*1.5 point, and a set of two upfloaters is needed. Then {#1,#2} {#1,#3} {#2,#3} are*
*part of the same container; {#1,#4} {#1,#5} {#2,#4} {#2,#5} {#3,#4} {#3,#5} are part of another container; {#1,#6} {#2,#6} {#3,#6} are part of a third container;*
*{#4,#5} are part of a fourth container; {#4,#6} {#5,#6} are part of a fifth (and last) container.*

The containers are sorted along the lines described by criterion C.6.
The sets belonging to each container are sorted according to the lexicographic order of the sequence numbers they are formed of.

**Sorting the shifters**
*Any player in the bracket having a colour preference for White (Black) is a possible White (resp. Black) shifter. The need for shifters arises when, in order to make or complete a pairing, some players seeking a colour are shifted to the subgroup of players initially seeking the other colour.*
*The possible White (resp. Black) shifters constitute the selected pool (see D.0.a).*
a. White seekers are sorted in order of ascending ARO or, when AROs are equal, highest initial ranking.
Black seekers are sorted according to their initial ranking.
b. With such sorted list, assign the sequence numbers, starting with the player in the (remaining) middle of the list or, when two players are in the (remaining) middle, to the one with a higher position in the list.

*Example:*
*if the sorted list contains seven players (in order: A, B, C, D, E, F, G), #1 goes to D (middle of the seven players), #2 to C (higher between C and E, both in the middle of the remaining six players),*
*#3 to E (middle of the remaining five players), #4 to B, #5 to F, #6 to A, #7 to G.*


**Rationale:**
Since the system tries to equalize the ARO of the White seekers (while the Black seekers are "tools" for reaching this goal), it is statistically better to shift White seekers with AROs in the middle *(their ARO is probably already equalized)*, and Black seekers with ratings in the middle *(because ARO equalization is usually performed better by Black seekers with extreme ratings)*.

D.3 a. The players in the G2 pool are assigned sequence numbers according to their initial ranking.
The sorted sets of G2 players are also called Transpositions.
*Note:*
*If, for instance, players A, B, C (listed according to the initial ranking) are in G2, the different Transpositions are {A, B, C}{A, C, B} {B, A, C} {B, C, A} {C, A, B} and {C, B, A}, in that*
*exact order.*
