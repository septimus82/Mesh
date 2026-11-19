# B-01b evidence

- base_repro_a.txt / head_repro_a.txt: snapshot function, two sprites sharing id "orc" (live x/y 15,16 and 210,310). Base lost the first sprite's move (10,10 = authored); head keeps both.
- base_real.txt / head_real.txt: real hidden GameWindow + production SaveManager (real_repro.py, disposable starter project). Base saves the first twin at its authored x=300 (move to 317 lost); head saves 317. Reloaded tags still show hp11 for both on head: load composes by id (saved_world.compose) - B-01, not changed here.
- base_tests.txt: new tests on the base implementation: 7 failed, 6 passed (the 6 golden no-duplicate cases pass on both).
- base_gpu_test.txt: the real-window test failing on the base.

## Update (load side, saved_world.compose)
head_real.txt now shows the reload giving hp30 / hp11 to the right twins (compose pairs the k-th saved entity of an id with the k-th authored entry). base_compose_tests.txt: new compose tests on the base compose: 3 failed, 6 passed. base_gpu_test.txt: real-window test (now asserting tags) failing on the base compose.
