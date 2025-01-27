# Impact of Machine Learning in some phases of Autonomous System Engineering

Artificial intelligence and machine learning have attracted significant interest as enablers of autonomous systems. These techniques suggest the need for formal engineering methods to evolve and adapt. 

## ML and AS's reliability
It is important to recognize machine learning as an enabler of autonomy that resides in this kind of software. Machine learning components perform the task of perception and their outputs inform decision making, which can range from simple deterministic cases to advanced rule-based artificial intelligence, after which the system executes the actions. There are two main differences between reliability engineering in ML and non-ML autonomous systems:
* For studying the reliability of a non-ML software is usually used the "Growth Model", in which is represented the growth of the reliability in term of time. In ML systems, time is represented by iterations of learning (epochs) and reliability is represented by the fraction of correct predictions divided by the total number of predictions (accuracy). 
* In ML-based autonomous systems is important to face the problem of the overfitting. To resolve this issue are usually used techniques like cross validation or regularization.

## ML and AS's testing
Machine learning algorithms enable autonomous systems to make decisions, which are prone to failures. Consider a simplified scenario in which the AS is a vehicle faced with the binary classification problem of pedestrians. Potential failures could be:
* False positives: stopping for a nonexistent pedestrian.
* False negatives: non stopping for a pedestrian.
Clearly a false negative is significantly more costly than a false positive, so the cost of misclassification need not to be symmetric as it is in traditional methods, so they are inadequate. To address these problems, testing must quantify the probability of entries in the confusion matrix to express cost.  