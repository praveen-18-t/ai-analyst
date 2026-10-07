import { AuthenticationDetails, CognitoUser, CognitoUserPool } from "amazon-cognito-identity-js";

const poolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID;
const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
export const authEnabled = !!(poolId && clientId);

const pool = authEnabled ? new CognitoUserPool({ UserPoolId: poolId!, ClientId: clientId! }) : null;

export function currentToken(): Promise<string | null> {
  if (!pool) return Promise.resolve(null);
  const user = pool.getCurrentUser();
  if (!user) return Promise.resolve(null);
  return new Promise((resolve) =>
    user.getSession((err: any, session: any) => resolve(err || !session?.isValid() ? null : session.getIdToken().getJwtToken()))
  );
}

export function signIn(username: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: username, Pool: pool! });
    user.authenticateUser(new AuthenticationDetails({ Username: username, Password: password }), {
      onSuccess: () => resolve(),
      onFailure: (e) => reject(e),
      newPasswordRequired: () => reject(new Error("A new password is required. Set one via the Cognito hosted UI or AWS CLI first.")),
    });
  });
}

export function signOut() {
  pool?.getCurrentUser()?.signOut();
}
