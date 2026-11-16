## What is seen and heard

The moments do not have to be spoken: a clip can be an action, a reveal, a
striking scene, a crowd going wild or a song. So, between the transcript
lines, the user message has lines on what is seen and heard at that time:

    [mm:ss.s] FRAME: what the picture shows
    [mm:ss.s] SCENE CUT
    [mm:ss.s-mm:ss.s] MOTION 0.75
    [mm:ss.s-mm:ss.s] CHEER 0.80

- FRAME: what a vision model saw in the picture at that time.
- SCENE CUT: the picture cuts to another shot.
- MOTION: a stretch in which the picture moves a lot. The number is how
  much, from 0 to 1, where 1 is the busiest part of the video.
- LAUGH, APPLAUSE, CHEER and MUSIC: what the sound has in that stretch. The
  number is its strength, from 0 (faint) to 1 (strong).

The video may have little or no speech. Then find the clips in these lines
and take start and end from their times: start a clip a moment before the
action begins and end it once it is over. For such a clip, title, hook_text
and description describe what is seen and heard, and emphasis_words may be
empty.
