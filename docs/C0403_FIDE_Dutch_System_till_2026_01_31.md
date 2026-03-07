# C.04.3 FIDE (Dutch) System (effective till 31 January 2026)

Source: https://handbook.fide.com/chapter/C0403Till2026

Retrieved: 2026-03-07
| Version approved at the 87th FIDE Congress in Baku 2016.
**Terms and Definitions** and **Pairing Guidelines For Programmers** added at the 88th FIDE Congress in Goynuk 2017. 
 See [https://spp.fide.com/fide-dutch-extras/](https://spp.fide.com/fide-dutch-extras/) |  |  |  |
| --- | --- | --- | --- |
| A | **Introductory Remarks and Definitions** |  |  |
|  | A.1 | **Initial ranking list** |  |
|  |  | See C.04.2.B (General Handling Rules - Initial order) |  |
|  | A.2 | **Order** |  |
|  |  | For pairings purposes only, the players are ranked in order of, respectively |  |
|  |  | a | score |
|  |  | b | pairing numbers assigned to the players accordingly to the initial ranking list and subsequent modifications depending on possible late entries or rating adjustments |
|  | A.3 | **Scoregroups and pairing brackets** |  |
|  |  | A scoregroup is normally composed of (all) the players with the same score. The only exception is the special "collapsed" scoregroup defined in A.9. 
 A (pairing) bracket is a group of players to be paired. It is composed of players coming from one same scoregroup (called resident players) and of players who remained unpaired after the pairing of the previous bracket. 
 A (pairing) bracket is homogeneous if all the players have the same score; otherwise it is heterogeneous. 
 A remainder (pairing bracket) is a sub-bracket of a heterogeneous bracket, containing some of its resident players *(see B.3 for further details)*. |  |
|  | A.4 | **Floaters and floats** |  |
|  |  | a | A downfloater is a player who remains unpaired in a bracket, and is thus moved to the next bracket. In the destination bracket, such players are called "moved-down players" (MDPs for short). |
|  |  | b | After two players with different scores have played each other in a round, the higher ranked player receives a downfloat, the lower one an upfloat. 
 A player who, for whatever reason, does not play in a round, also receives a downfloat. |
|  | A.5 | **Byes** |  |
|  |  | See C.04.1.c *(Should the number of players to be paired be odd, one player* *is unpaired. This player receives a pairing-allocated bye: no opponent, no colour and as many points as are rewarded for a win, unless the regulations of the tournament state otherwise)*. |  |
|  | A.6 | **Colour differences and colour preferences** |  |
|  |  | The colour difference of a player is the number of games played with white minus the number of games played with black by this player. 
 The colour preference is the colour that a player should ideally receive for the next game. It can be determined for each player who has played at least one game. |  |
|  |  | a | An absolute colour preference occurs when a player’s colour difference is greater than +1 or less than -1, or when a player had the same colour in the two latest rounds he played. The preference is white when the colour difference is less than -1 or when the last two games were played with black. The preference is black when the colour difference is greater than +1, or when the last two games were played with white. |
|  |  | b | A strong colour preference occurs when a player‘s colour difference is +1 (preference for black) or -1 (preference for white). |
|  |  | c | A mild colour preference occurs when a player’s colour difference is zero, the preference being to alternate the colour with respect to the previous game he played. |
|  |  | d | Players who did not play any games have no colour preference (the preference of their opponents is granted). |
|  | A.7 | **Topscorers** |  |
|  |  | Topscorers are players who have a score of over 50% of the maximum possible score when pairing the final round of the tournament. |  |
|  | A.8 | **Pairing Score Difference (PSD)** |  |
|  |  | The pairing of a bracket is composed of pairs and downfloaters. 
 Its Pairing Score Difference is a list of score-differences *(SD, see below)*, sorted from the highest to the lowest. 
 For each pair in a pairing, the SD is defined as the absolute value of the difference between the scores of the two players who constitute the pair. 
 For each downfloater, the SD is defined as the difference between the score of the downfloater, and an artificial value that is one point less than the score of the lowest ranked player of the current bracket (even when this yields a negative value). |  |
|  |  | *Note:**The artificial value defined above was chosen in order to be strictly less than the lowest score of the bracket, and generic enough to work with different scoring-point systems and in presence of non-existent, empty or sparsely populated brackets that may follow the current one.* |  |
|  |  | PSD(s) are compared lexicographically *(i.e. their respective SD(s) are compared one by one from first to last - in the first corresponding SD(s) that are different, the smallest one defines the lower PSD)*. |  |
|  | A.9 | **Round-Pairing Outlook** |  |
|  |  | The pairing of a round (called round-pairing) is complete if all the players (except at most one, who receives the pairing-allocated bye) have been paired and the absolute criteria C1-C3 have been complied with. 
 If it is impossible to complete a round-pairing, the arbiter shall decide what to do. Otherwise, the pairing process starts with the top scoregroup, and continues bracket by bracket until all the scoregroups, in descending order, have been used and the round-pairing is complete. 
 However, if, during this process, the downfloaters (possibly none) produced by the bracket just paired, together with all the remaining players, do not allow the completion of the round-pairing, a different processing route is followed. The last paired bracket is called Penultimate Pairing Bracket (PPB). The score of its resident players is called the "collapsing" score. All the players with a score lower than the collapsing score constitute the special "collapsed" scoregroup mentioned in A.3. 
 The pairing process resumes with the re-pairing of the PPB. Its downfloaters, together with the players of the collapsed scoregroup, constitute the Collapsed Last Bracket (CLB), the pairing of which will complete the round-pairing. |  |
|  |  | *Note:**Independently from the route followed, the assignment of the pairing-allocated bye (see C.2) is part of the pairing of the last bracket.* |  |
|  |  | Section B describes the pairing process of a single bracket. 
 Section C describes all the criteria that the pairing of a bracket has to satisfy. 
 Section E describes the colour allocation rules that determine which players will play with white. |  |
| B | **Pairing Process for a bracket** |  |  |
|  | B.1 | **Parameters definitions** |  |
|  |  | a | M0 is the number of MDP(s) coming from the previous bracket. It may be zero. |
|  |  | b | MaxPairs is the maximum number of pairs that can be produced in the bracket under consideration *(see C.5)*. |
|  |  |  | *Note:**MaxPairs is usually equal to the number of players divided by two and rounded downwards. However, if, for instance, M0 is greater than the number of resident players, MaxPairs is at most equal to the number of resident players.* |
|  |  | c | M1 is the maximum number of MDP(s) that can be paired in the bracket *(see C.6)*. |
|  |  |  | *Note:**M1 is usually equal to the number of MDPs coming from the previous bracket, which may be zero. However, if, for instance, M0 is greater than the number of resident players, M1 is at most equal to the number of resident players.* 
 *Of course, M1 can never be greater than MaxPairs.* |
|  | B.2 | **Subgroups (original composition)** |  |
|  |  | To make the pairing, each bracket will be usually divided into two subgroups, called S1 and S2. 
 S1 initially contains the highest N1 players (sorted according to A.2), where N1 is either M1 *(in a heterogeneous bracket)* or MaxPairs *(otherwise)*. 
 S2 initially contains all the remaining resident players. 
 When M1 is less than M0, some MDPs are not included in S1. The excluded MDPs *(in number of M0 - M1)*, who are neither in S1 nor in S2, are said to be in a *Limbo*. |  |
|  |  | *Note:* | *the players in the Limbo cannot be paired in the bracket, and are thus bound to double-float.* |
|  | B.3 | **Preparation of the candidate** |  |
|  |  | S1 players are tentatively paired with S2 players, the first one from S1 with the first one from S2, the second one from S1 with the second one from S2 and so on. 
 In a homogeneous bracket: the pairs formed as explained above and all the players who remain unpaired (bound to be downfloaters) constitute a candidate (pairing). 
 In a heterogeneous bracket: the pairs formed as explained above match M1 MDPs from S1 with M1 resident players from S2. This is called a MDP-Pairing. The remaining resident players *(if any)* give rise to the remainder *(see A.3)*, which is then paired with the same rules used for a homogeneous bracket. |  |
|  |  | *Note:* | *M1 may sometimes be zero. In this case, S1 will be empty and the MDP(s) will all be in the Limbo. Hence, the pairing of the heterogeneous bracket will proceed directly to the remainder.* |
|  |  | A candidate (pairing) for a heterogeneous bracket is composed by a MDP-Pairing and a candidate for the ensuing remainder. All players in the Limbo are bound to be downfloaters. |  |
|  | B.4 | **Evaluation of the candidate** |  |
|  |  | If the candidate built as shown in B.3 complies with all the absolute and completion criteria *(from C.1 to C.4)*, and all the quality criteria from C.5 to C.19 are fulfilled, the candidate is called "perfect" and is (immediately) accepted. Otherwise, apply B.5 in order to find a perfect candidate; or, if no such candidate exists, apply B.8. |  |
|  | B.5 | **Actions when the candidate is not perfect** |  |
|  |  | The composition of S1, Limbo and S2 has to be altered in such a way that a different candidate can be produced. 
 The articles B.6 (for homogeneous brackets and remainders) and B.7 (for heterogeneous brackets) define the precise sequence in which the alterations must be applied. 
 After each alteration, a new candidate shall be built *(see B.3)* and evaluated *(see B.4)*. |  |
|  | B.6 | **Alterations in homogeneous brackets or remainders** |  |
|  |  | Alter the order of the players in S2 with a transposition *(see D.1)*. If no more transpositions of S2 are available for the current S1, alter the original S1 and S2 *(see B.2)* applying an exchange of resident players between S1 and S2 *(see D.2)* and reordering the newly formed S1 and S2 according to A.2. |  |
|  | B.7 | **Alterations in heterogeneous brackets** |  |
|  |  | Operate on the remainder with the same rules used for homogeneous brackets *(see B.6)*. |  |
|  |  | *Note:* | *The original subgroups of the remainder, which will be used throughout all the remainder pairing process, are the ones formed right after the MDP-Pairing. They are called S1R and S2R (to avoid any confusion with the subgroups S1 and S2 of the complete heterogeneous bracket)*. |
|  |  | If no more transpositions and exchanges are available for S1R and S2R, alter the order of the players in S2 with a transposition *(see D.1)*, forming a new MDP-Pairing and possibly a new remainder (to be processed as written above). 
 If no more transpositions are available for the current S1, alter, if possible (i.e. if there is a Limbo), the original S1 and Limbo *(see B.2)*, applying an exchange of MDPs between S1 and the Limbo *(see D.3)*, reordering the newly formed S1 according to A.2 and restoring S2 to its original composition. |  |
|  | B.8 | **Actions when no perfect candidate exists** |  |
|  |  | Choose the best available candidate. In order to do so, consider that a candidate is better than another if it better satisfies a quality criterion (C5-C19) of higher priority; or, all quality criteria being equally satisfied, it is generated earlier than the other one in the sequence of the candidates *(see B.6 or B.7)*. |  |
| C | **Pairing Criteria** |  |  |
|  | **Absolute Criteria** |  |  |
|  | No pairing shall violate the following absolute criteria: |  |  |
|  | C.1 | see C.04.1.b *(Two players shall not play against each other more than once)* |  |
|  | C.2 | see C.04.1.d *(A player who has already received a pairing-allocated bye, or has already scored a (forfeit) win due to an opponent not appearing in time, shall not receive the pairing-allocated bye)*. |  |
|  | C.3 | non-topscorers *(see A.7)* with the same absolute colour preference *(see A6.a)* shall not meet *(see C.04.1.f and C.04.1.g).* |  |
|  | **Completion Criterion** |  |  |
|  | C.4 | if the current bracket is the PPB *(see A.9)*: choose the set of downfloaters in order to complete the round-pairing. |  |
|  | **Quality Criteria** |  |  |
|  | To obtain the best possible pairing for a bracket, comply as much as possible with the following criteria, given in descending priority: |  |  |
|  | C.5 | maximize the number of pairs *(equivalent to: minimize the number of downfloaters).* |  |
|  | C.6 | minimize the PSD (*This basically means: maximize the number of paired MDP(s); and, as far as possible, pair the ones with the highest scores*). |  |
|  | C.7 | if the current bracket is neither the PPB nor the CLB *(see A.9)*: choose the set of downfloaters in order first to maximize the number of pairs and then to minimize the PSD *(see C.5 and C.6)* in the following bracket *(just in the following bracket).* |  |
|  | C.8 | minimize the number of topscorers or topscorers' opponents who get a colour difference higher than +2 or lower than -2. |  |
|  | C.9 | minimize the number of topscorers or topscorers' opponents who get the same colour three times in a row. |  |
|  | C.10 | minimize the number of players who do not get their colour preference. |  |
|  | C.11 | minimize the number of players who do not get their strong colour preference. |  |
|  | C.12 | minimize the number of players who receive the same downfloat as the previous round. |  |
|  | C.13 | minimize the number of players who receive the same upfloat as the previous round. |  |
|  | C.14 | minimize the number of players who receive the same downfloat as two rounds before. |  |
|  | C.15 | minimize the number of players who receive the same upfloat as two rounds before. |  |
|  | C.16 | minimize the score differences of players who receive the same downfloat as the previous round. |  |
|  | C.17 | minimize the score differences of players who receive the same upfloat as the previous round. |  |
|  | C.18 | minimize the score differences of players who receive the same downfloat as two rounds before. |  |
|  | C.19 | minimize the score differences of players who receive the same upfloat as two rounds before. |  |
| D | **Rules for the sequential generation of the pairings** |  |  |
|  | Before any transposition or exchange take place, all players in the bracket shall be tagged with consecutive in-bracket sequence-numbers (BSN for short) representing their respective ranking order (according to A.2) in the bracket *(i.e. 1, 2, 3, 4, ...)*. |  |  |
|  | D.1 | **Transpositions in S2** |  |
|  |  | A transposition is a change in the order of the BSNs *(all representing resident players)* in S2. 
 All the possible transpositions are sorted depending on the lexicographic value of their first N1 BSN(s), where N1 is the number of BSN(s) in S1 (*the remaining BSN(s) of S2 are ignored in this context, because they represent players bound to constitute the remainder in case of a heterogeneous bracket; or bound to downfloat in case of a homogeneous bracket - e.g. in a 11-player homogeneous bracket, it is 6-7-8-9-10, 6-7-8-9-11, 6-7-8-10-11, ..., 6-11-10-9-8, 7-6-8-9-10, ..., 11-10-9-8-7 (720 transpositions); if the bracket is heterogeneous with two MDPs, it is: 3-4, 3-5, 3-6, ..., 3-11, 4-3, 4-5, ..., 11-10 (72 transpositions))*. |  |
|  | D.2 | **Exchanges in homogeneous brackets or remainders****(original S1 ↔ original S2)** |  |
|  |  | An exchange in a homogeneous brackets (also called a resident-exchange) is a swap of two equally sized groups of BSN(s) *(all representing resident players)* between the original S1 and the original S2. 
 In order to sort all the possible resident-exchanges, apply the following comparison rules between two resident-exchanges in the specified order *(i.e. if a rule does not discriminate between two exchanges, move to the next one)*. 
 The priority goes to the exchange having: |  |
|  |  | a | the smallest number of exchanged BSN(s) *(e.g exchanging just one BSN is better than exchanging two of them).* |
|  |  | b | the smallest difference between the sum of the BSN(s) moved from the original S2 to S1 and the sum of the BSN(s) moved from the original S1 to S2*(e.g. in a bracket containing eleven players, exchanging 6 with 4 is better than exchanging 8 with 5; similarly exchanging 8+6 with 4+3 is better than exchanging 9+8 with 5+4; and so on)*. |
|  |  | c | the highest different BSN among those moved from the original S1 to S2*(e.g. moving 5 from S1 to S2 is better than moving 4; similarly, 5-2 is better than 4-3; 5-4-1 is better than 5-3-2; and so on)*. |
|  |  | d | the lowest different BSN among those moved from the original S2 to S1*(e.g. moving 6 from S2 to S1 is better than moving 7; similarly, 6-9 is better than 7-8; 6-7-10 is better than 6-8-9; and so on)*. |
|  | D.3 | **Exchanges in heterogeneous brackets****(original S1 ↔ original Limbo)** |  |
|  |  | An exchange in a heterogeneous bracket (also called a MDP-exchange) is a swap of two equally sized groups of **BSN(s)** *(all representing MDP(s))* between the original S1 and the original Limbo. 
 In order to sort all the possible MDP-exchanges, apply the following comparison rules between two MDP-exchanges in the specified order *(i.e. if a rule does not discriminate between two exchanges, move to the next one)* to the players that are in the new S1 after the exchange. 
 The priority goes to the exchange that yields a S1 having: |  |
|  |  | a | the highest different score among the players represented by their BSN *(this comes automatically in complying with the C.6 criterion, which says to minimize the PSD of a bracket)*. |
|  |  | b | the lowest lexicographic value of the BSN(s) (sorted in ascending order). |
|  | Any time a sorting has been established, any application of the corresponding D.1, D.2 or D.3 rule, will pick the next element in the sorting order. |  |  |
| E | **Colour Allocation rules** |  |  |
|  | *Initial-colour* 
 It is the colour determined by drawing of lots before the pairing of the first round. |  |  |
|  | For each pair apply (with descending priority): |  |  |
|  | E.1 | Grant both colour preferences. |  |
|  | E.2 | Grant the stronger colour preference. If both are absolute (topscorers, see A.7) grant the wider colour difference (see A.6). |  |
|  | E.3 | Taking into account C.04.2.D.5, alternate the colours to the most recent time in which one player had white and the other black. |  |
|  | E.4 | Grant the colour preference of the higher ranked player. |  |
|  | E.5 | If the higher ranked player has an odd pairing number, give him the initial-colour; otherwise give him the opposite colour. |  |
|  |  | *Note:**Always consider sections C.04.2.B/C (Initial Order/Late Entries) for the proper management of the pairing numbers.* |  |
