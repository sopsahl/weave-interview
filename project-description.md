# Engineering Impact Dashboard Outline

Given the instructions in `./project-instructions.md`, help me design and plan for the implementation of the engineering impact dashboard for PostHog. We only have 90 minutes to get this done. As a result, we are not building a perfect tool. We just need something that satisfies all of the prerequisites that are outlined in the instructions. The tasks and important notes are included below:

1. How do we access engineer data? My inital ideas are to use three categories:
    - Collaboration: How much an engineer reviews PRs, how often those reviews are responded to, etc.
    - Ownership: Issues/Bugs/Incidences. This might include the amount that a specific engineer works on a key portion of the repository.
    - Output: This is a more direct measure of their output, measuring lines of code, number of PRs, PR activity, etc.

    For this section, I want to have as many visualizations as possible with each of the metrics we decide to track. Feel free to brainstorm with me on actionable metrics that require little computation from the data accessible through GitHub GrapQL.

2. How do we combine these metrics to rank engineer output? I think there should be two levels of abstraction. One, we will have a percentage of each of the three categories as a slider, or similar feature, that the user can control. This will change the weighting of the scores from each of the three categories dynamically on the webpage. Second, we have individual weights applied to each metric that are generated as a result of some exploration by us prior to the conclusion of this project. As a result, we can precompute many of the statistics ahead of time to save on website load time.

3. How do we visualize the results? This can be split into mutiple categories. One, we need to host a website within 90 minutes, so rapid iteration and easy usage are key for the language and infrastructure that we decide to use. I am leaning towards Streamlit because it is Python based, but if there is an alternative you think is better, let me know in the process of planning. Second, we want the visualizations to be highly interpretable. As a result, I would like graphs for each of the metrics for every engineer, with a short explanation (maybe in a pop-up) of what it is measuing and what that means. Finally, I want a way to combine the three categories with a slider or some other method of ranking to choose a top engineer at the company. That graph should be pretty, and also describe how the scores are calculated and combined. 
