#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { BaseStackProps } from '../lib/types';
import {
  DockerImageStack,
  AgentCoreStack
} from '../lib/stacks';

const app = new cdk.App();
const deploymentProps: BaseStackProps = {
  appName: "l27agentcore",
  // Use current CLI configuration for account/region
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION
  },
}
const dockerImageStack = new DockerImageStack(app, `l27agentcore-DockerImageStack`, deploymentProps);
const agentCoreStack = new AgentCoreStack(app, `l27agentcore-AgentCoreStack`, {
  ...deploymentProps,
  imageUri: dockerImageStack.imageUri
});
agentCoreStack.addDependency(dockerImageStack);