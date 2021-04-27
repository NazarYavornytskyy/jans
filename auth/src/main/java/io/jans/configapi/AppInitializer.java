/*
 * Janssen Project software is available under the MIT License (2008). See http://opensource.org/licenses/MIT for full text.
 *
 * Copyright (c) 2020, Janssen Project
 */

package io.jans.configapi;

import io.jans.as.common.service.common.ApplicationFactory;
import io.jans.configapi.configuration.ConfigurationFactory;
import io.jans.exception.ConfigurationException;
import io.jans.exception.OxIntializationException;
import io.jans.orm.PersistenceEntryManager;
import io.jans.orm.PersistenceEntryManagerFactory;
import io.jans.orm.service.PersistanceFactoryService;
import io.jans.service.cdi.event.ApplicationInitialized;
import io.jans.service.cdi.event.ApplicationInitializedEvent;
import io.jans.service.cdi.event.LdapConfigurationReload;
import io.jans.service.cdi.util.CdiUtil;
import io.jans.util.StringHelper;
import io.jans.util.security.StringEncrypter;
import io.jans.util.security.StringEncrypter.EncryptionException;
//import io.quarkus.runtime.ShutdownEvent;
//import io.quarkus.runtime.StartupEvent;
import org.jboss.resteasy.plugins.server.servlet.ResteasyContextParameters;
import org.slf4j.Logger;

import javax.annotation.PostConstruct;
import javax.ejb.DependsOn;
import javax.enterprise.context.ApplicationScoped;
import javax.enterprise.context.BeforeDestroyed;
import javax.enterprise.context.Initialized;
import javax.enterprise.event.Event;
import javax.enterprise.event.Observes;
import javax.enterprise.inject.Alternative;
import javax.enterprise.inject.Instance;
import javax.enterprise.inject.Produces;
import javax.enterprise.inject.spi.BeanManager;
import javax.inject.Inject;
import javax.inject.Named;
import javax.enterprise.inject.spi.BeanManager;
import javax.inject.Inject;
import javax.inject.Named;

@ApplicationScoped
public class AppInitializer {

    @Inject
    Logger logger;

    @Inject
    private Event<ApplicationInitializedEvent> eventApplicationInitialized;

    @Inject
    @Named(ApplicationFactory.PERSISTENCE_ENTRY_MANAGER_NAME)
    Instance<PersistenceEntryManager> persistenceEntryManagerInstance;

    @Inject
    BeanManager beanManager;

    @Inject
    ConfigurationFactory configurationFactory;

    @Inject
    private PersistanceFactoryService persistanceFactoryService;

    void onStart(@Observes @Initialized(ApplicationScoped.class) Object init) {
        logger.info("=================================================================");
        logger.info("=============  STARTING API APPLICATION  ========================");
        logger.info("=================================================================");
        System.setProperty(ResteasyContextParameters.RESTEASY_PATCH_FILTER_DISABLED, "true");
        this.configurationFactory.create();
        persistenceEntryManagerInstance.get();
        logger.info("=================================================================");
        logger.info("==============  APPLICATION IS UP AND RUNNING ===================");
        logger.info("=================================================================");
    }

    void onStop(/* @Observes ShutdownEvent ev */) {
        logger.info("================================================================");
        logger.info("===========  API APPLICATION STOPPED  ==========================");
        logger.info("================================================================");
    }

    @Produces
    @ApplicationScoped
    public ConfigurationFactory getConfigurationFactory() {
        return configurationFactory;
    }


    @Produces
    @ApplicationScoped
    @Named(ApplicationFactory.PERSISTENCE_ENTRY_MANAGER_NAME)
    public PersistenceEntryManager createPersistenceEntryManager() throws OxIntializationException {
        PersistenceEntryManagerFactory persistenceEntryManagerFactory = persistanceFactoryService
                .getPersistenceEntryManagerFactory(configurationFactory.getPersistenceConfiguration());
        PersistenceEntryManager persistenceEntryManager = persistenceEntryManagerFactory
                .createEntryManager(configurationFactory.getDecryptedConnectionProperties());
        logger.debug("Created {} with operation service {}", persistenceEntryManager,
                persistenceEntryManager.getOperationService());
        return persistenceEntryManager;
    }

    public void recreatePersistanceEntryManager(@Observes @LdapConfigurationReload String event) {
        closePersistenceEntryManager();
        PersistenceEntryManager ldapEntryManager = persistenceEntryManagerInstance.get();
        persistenceEntryManagerInstance.destroy(ldapEntryManager);
        logger.debug("Recreated instance {} with operation service: {}", ldapEntryManager,
                ldapEntryManager.getOperationService());
    }

    private void closePersistenceEntryManager() {
        PersistenceEntryManager oldInstance = CdiUtil.getContextBean(beanManager, PersistenceEntryManager.class,
                ApplicationFactory.PERSISTENCE_ENTRY_MANAGER_NAME);
        if (oldInstance == null || oldInstance.getOperationService() == null)
            return;

        logger.debug("Attempting to destroy {} with operation service: {}", oldInstance,
                oldInstance.getOperationService());
        oldInstance.destroy();
        logger.debug("Destroyed {} with operation service: {}", oldInstance, oldInstance.getOperationService());
    }
}
