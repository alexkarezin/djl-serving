/*
 * Copyright 2022 Amazon.com, Inc. or its affiliates. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
 * with the License. A copy of the License is located at
 *
 * http://aws.amazon.com/apache2.0/
 *
 * or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
 * OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions
 * and limitations under the License.
 */
package ai.djl.python.engine;

import ai.djl.engine.EngineProvider;

/** {@code DsEngineProvider} is the DeepSpeed implementation of {@link EngineProvider}. */
public class DsEngineProvider extends PyEngineProvider {

    /** Constructs a new {@code DsEngineProvider} instance. */
    public DsEngineProvider() {
        mpiMode = true;
    }

    /** {@inheritDoc} */
    @Override
    public String getEngineName() {
        return "DeepSpeed";
    }

    /** {@inheritDoc} */
    @Override
    public int getEngineRank() {
        return PyEngine.RANK + 1;
    }

    /** {@code FtEngineProvider} is the alias of {@link DsEngineProvider}. */
    public static final class FtEngineProvider extends DsEngineProvider {

        /** {@inheritDoc} */
        @Override
        public String getEngineName() {
            return "FasterTransformer";
        }
    }
}
