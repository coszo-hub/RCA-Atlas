# Task recipes

Code for tasks a question may ask for ("write a script to plot this earthquake at AXCC1 with the response removed"):
for each task in `tasks.json`, its steps, a Python script in `recipes/` that has been run, what to change in it, its
pitfalls, the instruments it works for and its sources. Ask Atlas fetches a task's recipe for a request for code
(`task_recipes` collection, `src/atlas_worker/src/task_recipes.json`), with the download recipe of the instrument the
question names, and writes the script from the recipe's.

| Task | Script | Instruments |
|---|---|---|
| Plot an earthquake's waveform, response removed and bandpass filtered | `recipes/earthquake_waveform.py` | OO seismometers (EarthScope) |

## A task in `tasks.json`

`title`, `script`, `summary`, `steps` (each with why), `change` (the values a user changes; the Worker's prompt lets
Gemma change only these), `pitfalls`, `instruments` (a list the builder writes from the data recipes' service cache),
`sources` (title and URL; a title has no parentheses or semicolons, as each becomes a citation of its own; a value
from a paper names the paper), and `match`: `task` (words naming the task) and `about` (words naming its instruments).
A request for code gets the task whose `about` words it has and most of whose `task` words.

## Build

```sh
python src/task_recipes/build_task_recipes.py --test   # run each script in the sandbox, then write data/TaskRecipes
python src/task_recipes/build_task_recipes.py          # write data/TaskRecipes and task_recipes.json from the results
```

Scripts run in the download recipes' sandbox (`src/data_recipes/test_recipes.py`): a fresh container with no host
folder and a capped work folder. A script passes when it exits cleanly having written a file that is not empty; a
task that has not passed is left out. Check a new script's figure by eye on a real case before adding it.
