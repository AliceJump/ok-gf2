# One-Click Dailies

## Overview

Runs the daily routine in one click, working top to bottom. Every step can be switched on or off on
its own (marked with a star).

Game terms below use the wording from the Global / Steam client. See
[../glossary.md](../glossary.md) for the full mapping.

### Steps and run order

The steps and their order are defined in [DailyTask.py](../../src/tasks/DailyTask.py), in the
`tasks` list inside the `run` function. In short:

1. **Community daily check-in**: completes the daily tasks on the web community (needs a username and password)
2. **Mail**: claims every attachment in your mailbox
3. **Event reward track**: claims rewards from the Event reward track and its bonus stages
4. **Auto-Run Event Supply**: enters the current Time-Limited Event and runs its Supply stage
5. **Crew Deck activities**: runs Tea Time, Delicious Cuisine, and the reward pickup
6. **Crew Deck / Dispatch Room**: sends out and collects Dispatch Room assignments
7. **Claim free packs**: buys the free packs in the Shop
8. **Wishlist purchases**: one-click buys your Wishlist items in each shop (Furniture Shop, Platoon Shop, Dispatch Shop, Battlelog Trading, Neural Integration, Growth Stack)
9. **Auto-Farm Intelligence Puzzle**: spends Intelligence Puzzle on Supply Missions for upgrade materials
10. **Combat Exercises**: runs Combat Exercises battles
11. **Platoon / Gunsmoke Frontline**: completes Platoon tasks and Gunsmoke Frontline
12. **Claim Commission rewards**: claims the daily rewards from Commissions
13. **Voyage**: claims the daily progress rewards from Voyage, the monthly pass
14. **Boundary Push**: claims gathering and dispatch rewards from Boundary Push

## Step details

### Community daily check-in

> Checklist: a username and password must be filled in.

Completes the community daily tasks by simulating web requests. It signs in to the community with
your username and password and performs the daily check-in.

Options: `⭐Community Daily` `Username` `Password`

### Mail

> Checklist: the in-game mailbox is available.

Opens the mailbox and claims all mail attachments.

Options: `⭐Mail`

### Auto-Run Event Supply

> Checklist: the current Supply stage name must be filled in.

Opens the current Time-Limited Event and runs its Supply stage.

Every Event has a Supply stage, which is the one that costs Intelligence Puzzle. In a **small
event** it is simply labelled **Supply**, so you can leave the setting empty. In a **large event**
it is renamed after the event and split into parts, so you enter the event name without the part
suffix. For a stage shown as `铸碑者的黎明·上篇`, you would enter `铸碑者的黎明`.

Options: `⭐Auto-Run Event Supply` `Current Supply stage name`

### Crew Deck activities

> Checklist: the Crew Deck is available.

Runs Tea Time, Delicious Cuisine, and the reward pickup on the Crew Deck.

The Crew Deck is a walkable area, so these two settings are movement timings. The bot walks your
character to the coffee machine or the kitchen by holding the keys for the durations you set. You
will need to tune them yourself, since the right values depend on where your character starts.

- **Tea Time**: presses `A`, then `W`, then `D` to reach the coffee machine
- **Delicious Cuisine**: presses `S`, then taps `D` to reach the kitchen

Options: `⭐Crew Deck` `Tea Time` `Delicious Cuisine`

### Crew Deck / Dispatch Room

> Checklist: the Crew Deck is available and the Dispatch Room is unlocked.

Sends out Dispatch Room assignments and collects the finished ones.

Turning on `Start Loop` makes the program use the game's own auto-loop mode. When it does, it skips
Supply Missions, Auto-Farm Intelligence Puzzle, gold farming stages, and Combat Exercises, since the
game handles those itself.

Options: `⭐Crew Deck / Dispatch Room` `Start Loop`

### Auto-Farm Intelligence Puzzle

> Checklist: you have Intelligence Puzzle available and have picked a Supply Mission type.

Enters the matching Supply Mission and spends Intelligence Puzzle farming materials. Pick one of:

- **Equipment Analysis**: weapon EXP materials
- **In-Depth Search**: character EXP materials
- **Cognitive Configuration**: skill upgrade materials
- **Targeted Study**: a specific material you choose

Options: `⭐Auto-Farm Intelligence Puzzle` `Supply Mission type`

### Combat Exercises

Runs Combat Exercises battles until the daily attempts are used up.

Options: `⭐Combat Exercises`

### Platoon / Gunsmoke Frontline

> Checklist: you have joined a Platoon.

Completes the daily Platoon tasks and plays Gunsmoke Frontline.

Options: `⭐Platoon` `⭐Gunsmoke Frontline`

### Claim Commission rewards

Opens Commissions and claims the daily task rewards.

Options: `⭐Claim Commission Rewards`

### Voyage

Opens Voyage, the monthly pass, and claims the daily progress rewards.

Options: `⭐Voyage`

### Boundary Push

> Checklist: Boundary Push is unlocked.

Opens Boundary Push and claims the gathering and dispatch rewards.

Options: `⭐Boundary Push`

## Other options

1. **Confirm the in-game global auto-battle setting is enabled**: before running, you must turn on
   global auto-battle in the game at Settings -> Other -> Auto-Battle Settings
2. **Exit when finished**: closes the program once the task completes
