"""站点设置应用服务 — 单行配置的读取与更新"""

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.site_settings import SiteSettingsDTO, UpdateSiteSettingsDTO
from omichub.infrastructure.database.models.site_settings import SiteSettingModel


class SiteSettingsService:
    """站点设置服务"""

    _SINGLETON_ID = 1

    def __init__(self, db: AsyncSession):
        self._db = db

    async def _get_or_create(self) -> SiteSettingModel:
        model = await self._db.get(SiteSettingModel, self._SINGLETON_ID)
        if model is None:
            model = SiteSettingModel(id=self._SINGLETON_ID, registration_enabled=True)
            self._db.add(model)
            await self._db.flush()
        return model

    async def get_settings(self) -> SiteSettingsDTO:
        model = await self._get_or_create()
        return SiteSettingsDTO(registration_enabled=model.registration_enabled)

    async def is_registration_enabled(self) -> bool:
        model = await self._get_or_create()
        return model.registration_enabled

    async def update_settings(self, req: UpdateSiteSettingsDTO) -> SiteSettingsDTO:
        model = await self._get_or_create()
        model.registration_enabled = req.registration_enabled
        await self._db.flush()
        return SiteSettingsDTO(registration_enabled=model.registration_enabled)
