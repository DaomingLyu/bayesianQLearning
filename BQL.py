import gym
import numpy as np
import random
import math
from scipy.stats import t
from scipy import special
from scipy import integrate
import matplotlib.pyplot as plt
import sys
from algorithms.utils.utils import *
from scipy.stats import norm
from gym.envs.toy_text.frozen_lake import FrozenLakeEnv
from envs.nchain_discrete import NChainEnv

discount_factor = 0.99

def normal_gamma_pdf(mu, tau, mu0, lambd, alpha, beta):
    return beta ** alpha * np.sqrt(lambd) / (special.gamma(alpha) * np.sqrt(2*np.pi)) \
           * tau ** (alpha - 0.5) * np.exp(-beta * tau) * np.exp(-0.5 * lambd * (mu - mu0) ** 2)

class BQLearning(object):
    """
     Bayesian Q-Learning algorithm.
    "Bayesian Q-learning". Dearden,Friedman,Russell. 1998.
    """

    #Those are class variables
    # ACTION SELECTION TYPE
    Q_VALUE_SAMPLING = 0
    MYOPIC_VPI = 1

    # POSTERIOR UPDATE
    MOMENT_UPDATING = 0
    MIXTURE_UPDATING = 1    
    def __init__(self, sh, gamma=0.99, update_method=0, selection_method=1):


        self.NUM_STATES=sh[0]
        self.NUM_ACTIONS=sh[1]
        self.discount_factor=gamma
        self.update_method=update_method
        self.selection_method=selection_method
        
        #initialize the distributions
        self.NG = np.zeros(shape=sh,  dtype=(float,4))
        for state in range(self.NUM_STATES):
            for action in range(self.NUM_ACTIONS):
                self.NG[state][action][1]=3.#3.
                self.NG[state][action][2]=1.1#1.5  #alpha>1 ensures the normal-gamma dist is well defined
                self.NG[state][action][3]=0.75#0.75 #high beta to increase the variance of the prior distribution to explore more
        
    def update(self, state, action, reward, next_state, done):
        if self.update_method==BQLearning.MOMENT_UPDATING:
            self.moment_updating(state, action, reward, next_state, done)
        else :
            self.mixture_updating(state, action, reward, next_state, done)
            
    def moment_updating(self, state, action, reward, next_state, done):
        NG=self.NG
        mean=NG[state][action][0]
        lamb=NG[state][action][1]
        alpha=NG[state][action][2]
        beta=NG[state][action][3]

        if not done:

            #find best action at next state
            means=NG[next_state, :, 0]
            next_action=argmaxrand(means)

            mean_next=NG[next_state][next_action][0]
            lamb_next=NG[next_state][next_action][1]
            alpha_next=NG[next_state][next_action][2]
            beta_next=NG[next_state][next_action][3]

            #calculate the first two moments of the cumulative reward of the next state
            M1=reward+self.discount_factor*mean_next
            M2=reward**2+2*self.discount_factor*reward*mean_next+self.discount_factor**2*(((lamb_next+1)*beta_next)/(lamb_next*(alpha_next-1))+mean_next**2)

            #update the distribution (n=1)
            NG[state][action][0]=(lamb*mean+M1)/(lamb+1)
            NG[state][action][1]=lamb+1
            NG[state][action][2]=alpha+0.5
            NG[state][action][3]=beta+0.5*(M2-M1**2)+(lamb*(M1-mean)**2)/(2*(lamb+1))

        else:
            # update the distribution (n=1)
            NG[state][action][0] = (lamb * mean + reward) / (lamb + 1)
            NG[state][action][1] = lamb + 1
            NG[state][action][2] = alpha + 0.5
            NG[state][action][3] = beta + (lamb * (reward - mean) ** 2) / (2 * (lamb + 1))


    def mixture_updating(self, state, action, reward, next_state, done):
        NG=self.NG
        mean=NG[state][action][0]
        lamb=NG[state][action][1]
        alpha=NG[state][action][2]
        beta=NG[state][action][3]

        if not done:
            #find best action at next state
            means=NG[next_state, :, 0]
            next_action=argmaxrand(means)
            mean_next=NG[state][next_action][0]
            lamb_next=NG[state][next_action][1]
            alpha_next=NG[state][next_action][2]
            beta_next=NG[state][next_action][3]

            predictive_postetior_tointegrate = self.get_predictive_posterior_tointegrate(reward,mean, lamb, alpha, beta, mean_next, lamb_next, alpha_next, beta_next)
            ETaufun = lambda mu, tau, x: tau * predictive_postetior_tointegrate(mu, tau, x)
            EMuTaufun = lambda mu, tau, x: mu * tau * predictive_postetior_tointegrate(mu, tau, x)
            EMu2Taufun = lambda mu, tau, x: mu ** 2 * tau * predictive_postetior_tointegrate(mu, tau, x)
            ELogTaufun = lambda mu, tau, x: np.log(tau) * predictive_postetior_tointegrate(mu, tau, x)

            #We have to integrate over mu, tau and x. mu \in [-inf, inf], tau \in [0, \inf], x in [-inf, inf], so it is a triple integral
            ETau = integrate.tplquad(ETaufun, -np.inf, np.inf, lambda a: 0., lambda a: np.inf, lambda a,b: -np.inf, lambda a,b: np.inf)
            EMuTau = integrate.tplquad(EMuTaufun, -np.inf, np.inf, lambda a: 0., lambda a: np.inf, lambda a,b: -np.inf,lambda a,b: np.inf)
            EMu2Tau = integrate.tplquad(EMu2Taufun, -np.inf, np.inf, lambda a: 0., lambda a: np.inf, lambda a,b: -np.inf,lambda a,b: np.inf)
            ELogTau = integrate.tplquad(ELogTaufun, -np.inf, np.inf, lambda a: 0., lambda a: np.inf, lambda a,b: -np.inf,lambda a,b: np.inf)

            '''
            ETau, err=integrate.quad(self.getExpectedTau,-np.inf, np.inf, (reward,mean, lamb, alpha, beta, mean_next, lamb_next, alpha_next, beta_next))
            EMuTau, err=integrate.quad(self.getExpectedMuTau,-np.inf, np.inf, (reward,mean, lamb, alpha, beta, mean_next, lamb_next, alpha_next, beta_next))
            EMu2Tau, err=integrate.quad(self.getExpectedMu2Tau,-np.inf, np.inf, (reward,mean, lamb, alpha, beta, mean_next, lamb_next, alpha_next, beta_next))
            ELogTau, err=integrate.quad(self.getExpectedLogTau,-np.inf, np.inf, (reward,mean, lamb, alpha, beta, mean_next, lamb_next, alpha_next, beta_next))
            '''

            NG[state][action][0]=EMuTau/ETau
            NG[state][action][1]=1/(EMu2Tau-ETau*NG[state][action][0]**2)
            NG[state][action][2]=max(1.01, self.f(math.log(ETau)-ELogTau, num_iterations=20))
            NG[state][action][3]=float(NG[state][action][2]/ETau)

        else: #if done you don't need to propagate back anything so it is equivalent to moment update
            self.moment_updating(state, action, reward, next_state, done)

    def get_predictive_posterior_tointegrate(self, r, mean, lamb, alpha, beta, mean2, lamb2, alpha2, beta2):

        def predictive_postetior_tointegrate(mu, tau, x):
            M1 = r + self.discount_factor * x
            M2 = r ** 2 + 2 * self.discount_factor * r * x + self.discount_factor ** 2 * x ** 2
            new_mean = (lamb * mean + M1) / (lamb + 1)
            new_lambda = lamb + 1
            new_alpha = alpha + 0.5
            new_beta = beta + 0.5 * (M2 - M1 ** 2) + (lamb * (M1 - mean) ** 2) / (2 * (lamb + 1))

            return normal_gamma_pdf(mu, tau, new_mean, new_lambda, new_alpha, new_beta) * \
                t.pdf(x, 2 * alpha2, loc=mean2, scale=np.sqrt(beta2/alpha2 * (1 + 1./lamb2)))

        return predictive_postetior_tointegrate

    '''
    def getExpectedTau(self, Rt, r, mean, lamb, alpha, beta, mean2, lamb2, alpha2, beta2):
        M1=r+self.discount_factor*Rt
        M2=r**2+2*self.discount_factor*r*Rt+self.discount_factor**2*Rt**2
        mean=(lamb*mean+M1)/(lamb)
        lamb=lamb+1
        alpha=alpha+0.5
        beta=beta+0.5*(M2-M1**2)+(lamb*(M1-mean)**2)/(2*(lamb+1))
        ETau=alpha/beta
        PRt=norm(mean2,1/(math.sqrt(alpha2/beta2))).pdf(Rt) 
        return ETau*PRt
    
    def getExpectedMuTau(self,Rt, r,  mean, lamb, alpha, beta, mean2, lamb2, alpha2, beta2):
        M1=r+self.discount_factor*Rt
        M2=r**2+2*self.discount_factor*r*Rt+self.discount_factor**2*Rt**2
        mean=(lamb*mean+M1)/(lamb)
        lamb=lamb+1
        alpha=alpha+0.5
        beta=beta+0.5*(M2-M1**2)+(lamb*(M1-mean)**2)/(2*(lamb+1))
        EMuTau=(mean*alpha)/beta
        PRt=norm(mean2,1/(math.sqrt(alpha2/beta2))).pdf(Rt)
        return EMuTau*PRt
    
    def getExpectedMu2Tau(self,Rt, r,  mean, lamb, alpha, beta, mean2, lamb2, alpha2, beta2):
        M1=r+self.discount_factor*Rt
        M2=r**2+2*self.discount_factor*r*Rt+self.discount_factor**2*Rt**2
        mean=(lamb*mean+M1)/(lamb)
        lamb=lamb+1
        alpha=alpha+0.5
        beta=beta+0.5*(M2-M1**2)+(lamb*(M1-mean)**2)/(2*(lamb+1))
        EMu2Tau=(1/lamb)+(mean**2*alpha)/beta
        PRt=norm(mean2,1/(math.sqrt(alpha2/beta2))).pdf(Rt)
        return EMu2Tau*PRt
    
    def getExpectedLogTau(self,Rt, r, mean, lamb, alpha, beta, mean2, lamb2, alpha2, beta2):
        M1=r+self.discount_factor*Rt
        M2=r**2+2*self.discount_factor*r*Rt+self.discount_factor**2*Rt**2
        mean=(lamb*mean+M1)/(lamb)
        lamb=lamb+1
        alpha=alpha+0.5
        beta=beta+0.5*(M2-M1**2)+(lamb*(M1-mean)**2)/(2*(lamb+1))
        ELogTau=special.digamma(alpha)+np.log(beta)
        PRt=norm(mean2,1/(math.sqrt(alpha2/beta2))).pdf(Rt)
        return ELogTau*PRt
    '''
    def f(self, X, num_iterations):
        #initialize Y
        if X>=1.79:
            Y=(-0.5*np.exp(X))/(1-np.exp(X))
        else:
            Y=1
        for i in range(num_iterations):
            Y=-1/(X+special.digamma(1))
        return Y
    
    def g(self, X):
       return math.log(abs(X)) - special.digamma(X)
    
    def derG(self, X):
        return 1/X-special.polygamma(1, X)
        
    def select_action(self, state):
        if self.selection_method==BQLearning.Q_VALUE_SAMPLING:
            return self.Q_sampling_action_selection(self.NG, state)
        elif self.selection_method==BQLearning.MYOPIC_VPI:
            return self.Myopic_VPI_action_selection(self.NG, state)
        else :
            print("Random Action")
            return random.randint(0, self.NUM_ACTIONS-1)
    
    def Q_sampling_action_selection(self, NG, state):
        #Sample one value for each action
        samples=np.zeros(self.NUM_ACTIONS)
        for i in range(self.NUM_ACTIONS):
            mean=NG[state][i][0]
            lamb=NG[state][i][1]
            alpha=NG[state][i][2]
            beta=NG[state][i][3]

            #It is better to sample from the T-student because in this way we don't need to sample first \tau and then
            #\mu, this reduces the variance.
            #samples[i]=self.sample_NG(mean,lamb,alpha,beta)[0]

            samples[i] = np.random.standard_t(2*alpha) * np.sqrt(beta / (alpha * lamb)) + mean
        return argmaxrand(samples)
    
    def Myopic_VPI_action_selection(self, NG, state):
        #get best and second best action
        means=NG[state, :, 0]
        ranking=np.zeros(self.NUM_ACTIONS)
        best_action, second_best=self.get_2_best_actions(means)
        mean2 = NG[state][second_best][0]
        for i in range(self.NUM_ACTIONS):
            mean=NG[state][i][0]
            lamb=NG[state][i][1]
            alpha=NG[state][i][2]
            beta=NG[state][i][3]
            c=self.get_c_value(mean, lamb, alpha, beta)
            if i==best_action:
                ranking[i]= c +(mean2-mean)*getCumulativeDistribution(mean, lamb, alpha, beta, mean2)+mean
            else :
                ranking[i]= c +(mean-means[best_action])*(1-getCumulativeDistribution(mean, lamb, alpha, beta,means[best_action]))+mean
        return argmaxrand(ranking)

    def sample_NG(self, mean, lamb, alpha,beta):
        ##Sample x from a normal distribution with mean μ and variance 1 / ( λ τ ) 
        ##Sample τ from a gamma distribution with parameters alpha and beta 
        tau=np.random.gamma(alpha, beta)
        R=np.random.normal(mean, 1.0/(lamb*tau))
        return R, tau
        
    def set_selection_method(self,  method=1):
        if method in [BQLearning.Q_VALUE_SAMPLING,BQLearning.MYOPIC_VPI]:
            self.selection_method=method
        else:
            raise Exception('Selection Method not Valid')
    def set_update_method(self,  method=1):
        if method in [BQLearning.MOMENT_UPDATING,BQLearning.MIXTURE_UPDATING ]:
            self.update_method=method
        else:
            raise Exception('Update Method not Valid')
            
    def get_c_value(self, mean, lamb, alpha, beta):
        c=math.sqrt(beta)/((alpha-0.5)*math.sqrt(2*lamb)*special.beta(alpha, 0.5))
        c=c*math.pow(1+(mean**2/(2*alpha)), 0.5-alpha)
        return c
    
    def get_2_best_actions(self, A):
       best_two_indeces = np.argpartition(A, -2)
       if A[best_two_indeces[0]] > A[best_two_indeces[1]]:
            best_action = best_two_indeces[0]
            second_best_action = best_two_indeces[1]
       else:
            best_action = best_two_indeces[1]
            second_best_action = best_two_indeces[0]
       return best_action, second_best_action

        
    def get_v_function(self):
        return np.max(self.NG[:, :, 0], axis=1)

    def get_q_function(self):
        return self.NG[:, :, 0]

    def get_best_actions(self):
        return np.argmax(self.NG[:, :, 0], axis=1)
        
def simulate(env_name, num_episodes, len_episode, update_method, selection_method):
    # Initialize the  environment
    env = gym.make(env_name)
    NUM_STATES=env.observation_space.n
    NUM_ACTIONS=env.action_space.n
    NUM_EPISODES=num_episodes
    MAX_T=len_episode
    #update_method=agent.MIXTURE_UPDATING
    scores2=np.zeros(NUM_EPISODES)
    scores1=np.zeros(NUM_EPISODES)
    rewards=np.zeros(MAX_T)
    rewardsToGo=np.zeros(MAX_T)
    for episode in range(NUM_EPISODES):
        agent=BQLearning(sh=(NUM_STATES, NUM_ACTIONS))
        agent.set_selection_method(selection_method)
        agent.set_update_method(update_method)
        # Reset the environment
        obv = env.reset()
        # the initial state
        state_0 =obv
        #reset score
        score=0
        #learn 1 phase
        for i in range(MAX_T):
            action = agent.select_action(state_0)
            # Execute the action
            obv, reward, done, _ = env.step(action)
            score+=reward
            rewards[i]=reward
            # Observe the result
            state = obv
            # Update the Q based on the result
            agent.update(state_0, action, reward, state, done)
            # Setting up for the next iteration
            state_0 = state
            if done:
                #print("Episode %d finished after %f time steps, score=%d" % (episode, i, score))
                break
        scores1[episode]=score
        obv = env.reset()
        # the initial state
        state_0 =obv
        #reset score
        score=0
        
        for i in range(MAX_T):
            #env.render()
            # Select an action , specify method if needed
            action = agent.select_action(state_0)
            # Execute the action
            obv, reward, done, _ = env.step(action)
            score+=reward
            rewards[i]=reward
            # Observe the result
            state = obv
            # Update the Q based on the result
            agent.update(state_0, action, reward, state, done)
            # Setting up for the next iteration
            state_0 = state
            if done:
               #print("Episode %d finished after %f time steps, score=%d" % (episode, t, score))
               break
        for i in range(MAX_T):
            for j in range(i, MAX_T):
                rewardsToGo[i]+=rewards[j]*discount_factor**(j-i)
        scores2[episode]=score
    for i in range(MAX_T):
        rewardsToGo[i]=rewardsToGo[i]/NUM_EPISODES
    #print("Results:"+update_method+" "+selection_method)
    print("Avg Score Phase1:%f| std Phase 1:%f|Avg Score Phase2:%f| std Phase 2:%f|" % (np.mean(scores1), np.std(scores1), np.mean(scores2), np.std(scores2)))
    #print(agent.get_q_function())
    #plt.plot(range(MAX_T), rewardsToGo)

    plt.show()
def getCumulativeDistribution(mean, lamb, alpha, beta, x):
    rv=t(2*alpha)
    return rv.cdf((x-mean)*math.sqrt((lamb*alpha)/beta))

def print_V_function(V, num_states, name):
    if name=="NChain-v0":
        print(V)
    else:    
        n=int(math.sqrt(num_states))
        print("V function is:")
        for i in range(n):
            l=[]
            for j in range(n):
                l.append(V[(i*n)+j])
            print(l)
        
def print_best_actions(V, num_states, name):
    if name=="NChain-v0":
        l=[]
        for i in range(num_states):
            a=V[i]
            if a==0:
                l.append("Forward")
            else:
                l.append("Backward")
        print(l)
    else:
        n=int(math.sqrt(num_states))
        print("Best Action are:")
        for i in range(n):
            l=[]
            for j in range(n):
                a=V[i*n+j]
                if a==0:
                    l.append("Left")
                elif a==1:
                    l.append("Down")
                elif a==2:
                    l.append("Right")
                else:
                    l.append("Up")
            print(l)

if __name__ == "__main__":
    argv=sys.argv
    if len(argv)<2:
        print("usage BQL.py <env_name> <num_episodes> <len_episode>")
        env_name="NChain-v0"
    elif argv[1] in ["NChain-v0", "FrozenLake-v0"]:
        env_name=argv[1]
    else:
        env_name="FrozenLake-v0"
    if len(argv)>2:
        num_episodes=int(argv[2])
    else:
        print("Executing 10 episodes")
        num_episodes=10
    if len(argv)>3:
        len_episode=int(argv[3])
    else:
        print("Executing 1000 step episodes")
        len_episode=1000
    print("Testing on environment "+env_name)
    simulate(env_name, num_episodes, len_episode,BQLearning.MOMENT_UPDATING,BQLearning.Q_VALUE_SAMPLING  )
    simulate(env_name, num_episodes, len_episode,BQLearning.MOMENT_UPDATING,BQLearning.MYOPIC_VPI  )

